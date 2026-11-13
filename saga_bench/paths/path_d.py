"""Path D: choreography with on-demand election and graph-aware scheduling.

Normal operation is identical to Path B -- fully choreographed, no
coordinator. On failure:

1. A CompensationNeeded event is published.
2. All candidate services (every service that completed a step) race to
   acquire the lease for that saga_id via LeaseStore.try_acquire. Exactly
   one wins and becomes the temporary orchestrator for this saga instance
   only.
3. The winner reads SagaStore for which steps completed, builds the
   compensation sub-graph for exactly those steps, and dispatches
   compensations along the critical path: independent compensations
   concurrently, dependent ones in order.
4. Before dispatching any compensation, the orchestrator's dispatch marks
   it (via SagaStore.mark_compensated, which doubles as the idempotency
   key) so a re-elected orchestrator never re-runs one that already ran.
5. The lease is released on completion, or expires by TTL -- expiry
   triggers re-election, so a mid-rollback coordinator crash is
   recoverable.
6. After the rollback, no coordinator exists; the next saga runs pure
   choreography again.

A naive LIFO variant is available behind the same election (`scheduler=
"lifo"`), to isolate how much of the benefit comes from the
dependency-aware scheduler versus the election itself.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence, Set

from saga_bench.config import STEP_ORDER
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import CompensationGraph, default_graph
from saga_bench.lease_store import LeaseStore
from saga_bench.saga_store import SagaStore
from saga_bench.services import Service, build_services

PATH_NAME = "path_d"

LEASE_TTL_MS = 2000.0


def _dispatch_dependency_aware(
    saga_id: str,
    owner: str,
    sub_graph: CompensationGraph,
    services: Dict[str, Service],
    event_log: EventLog,
    saga_store: SagaStore,
    lease_store: LeaseStore,
    lease_renew_interval_ms: float,
) -> Set[str]:
    """Dispatch compensations respecting sub_graph's edges: independent
    steps run concurrently, dependent ones wait for their predecessors.
    Returns the set of steps this call actually ran (excludes duplicates
    skipped via the idempotency check)."""
    remaining = set(sub_graph.nodes)
    finished: Set[str] = set()
    ran: Set[str] = set()
    lock = threading.Lock()
    all_done = threading.Event()

    executor = ThreadPoolExecutor(max_workers=max(1, len(remaining)))
    futures = []

    def run_step(step: str) -> None:
        actually_ran = services[step].compensate(saga_id, PATH_NAME, event_log, saga_store=saga_store)
        with lock:
            if actually_ran:
                ran.add(step)
            finished.add(step)
            remaining.discard(step)
            newly_ready = sub_graph.ready_steps(remaining, finished)
            to_launch = list(newly_ready - _in_flight)
            _in_flight.update(to_launch)
            if not remaining:
                all_done.set()
        for nxt in to_launch:
            futures.append(executor.submit(run_step, nxt))

    _in_flight: Set[str] = set()
    with lock:
        initial_ready = sub_graph.ready_steps(remaining, finished)
        _in_flight.update(initial_ready)
        if not remaining:
            all_done.set()
    for step in initial_ready:
        futures.append(executor.submit(run_step, step))

    # Wait for completion while periodically renewing the lease so a long
    # rollback doesn't lose its own lease to a spurious re-election.
    while not all_done.wait(timeout=lease_renew_interval_ms / 1000.0):
        if not lease_store.renew(saga_id, owner, ttl_ms=LEASE_TTL_MS):
            break  # lost the lease (e.g. TTL expired) -- stop dispatching new work

    executor.shutdown(wait=True)
    return ran


def _dispatch_lifo(
    saga_id: str,
    owner: str,
    completed_order: List[str],
    services: Dict[str, Service],
    event_log: EventLog,
    saga_store: SagaStore,
) -> Set[str]:
    """Naive ablation: ignore the dependency graph entirely and compensate
    in strict reverse completion order, one at a time -- ablation baseline
    to isolate how much of Path D's benefit is the election versus the
    dependency-aware scheduler."""
    ran: Set[str] = set()
    for step in reversed(completed_order):
        if services[step].compensate(saga_id, PATH_NAME, event_log, saga_store=saga_store):
            ran.add(step)
    return ran


def run_path_d(
    saga_id: str,
    event_log: EventLog,
    fault_injector: FaultInjector,
    services: Optional[Dict[str, Service]] = None,
    saga_store: Optional[SagaStore] = None,
    lease_store: Optional[LeaseStore] = None,
    step_order: Sequence[str] = STEP_ORDER,
    graph: Optional[CompensationGraph] = None,
    scheduler: str = "dependency_aware",
    lease_renew_interval_ms: float = 50.0,
    owner_prefix: str = "",
) -> dict:
    if services is None:
        services = build_services()
    if saga_store is None:
        saga_store = SagaStore()
    if lease_store is None:
        lease_store = LeaseStore()
    if graph is None:
        graph = default_graph()

    event_log.append(saga_id, PATH_NAME, "saga_started")

    completed: List[str] = []
    failed_step: Optional[str] = None

    for step in step_order:
        if fault_injector.should_fail(saga_id, step):
            failed_step = step
            event_log.append(saga_id, PATH_NAME, "failure_detected", step)
            break
        services[step].execute(saga_id, PATH_NAME, event_log)
        saga_store.mark_completed(saga_id, step)
        completed.append(step)

    if failed_step is None:
        event_log.append(saga_id, PATH_NAME, "saga_succeeded")
        return {"saga_id": saga_id, "failed": False, "completed": completed, "compensated": []}

    event_log.append(saga_id, PATH_NAME, "rollback_started")

    # Every completed step's service is a candidate orchestrator. All race
    # for the lease; exactly one wins.
    candidates = list(completed)
    winner: Optional[str] = None
    election_lock = threading.Lock()

    def try_elect(candidate_step: str) -> None:
        nonlocal winner
        owner = f"{owner_prefix}{candidate_step}"
        if lease_store.try_acquire(saga_id, owner, ttl_ms=LEASE_TTL_MS):
            with election_lock:
                if winner is None:
                    winner = owner
                    event_log.append(saga_id, PATH_NAME, "elected_orchestrator", candidate_step)

    with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as election_executor:
        list(election_executor.map(try_elect, candidates))

    assert winner is not None, "election must always produce exactly one winner"

    completed_set = saga_store.completed_steps(saga_id)
    sub_graph = graph.subgraph(completed_set)

    if scheduler == "lifo":
        ran = _dispatch_lifo(saga_id, winner, completed, services, event_log, saga_store)
    else:
        ran = _dispatch_dependency_aware(
            saga_id, winner, sub_graph, services, event_log, saga_store, lease_store, lease_renew_interval_ms
        )

    lease_store.release(saga_id, winner)
    event_log.append(saga_id, PATH_NAME, "rollback_finished")

    return {
        "saga_id": saga_id,
        "failed": True,
        "failed_step": failed_step,
        "completed": completed,
        "compensated": sorted(ran),
        "orchestrator": winner,
    }
