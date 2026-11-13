"""Drives all saga runs for the experiment sweeps and turns the shared
EventLog into tidy per-saga-run metric rows.

Everything here is deterministic in the sense the spec cares about: no RNG
anywhere, fault injection is config-driven, and every saga_id maps to
exactly one scripted outcome. The one thing that is NOT bit-for-bit
reproducible between runs is the literal wall-clock timestamps, because
service work is real `time.sleep()` as required by the spec, and real
sleeps are subject to OS thread-scheduling jitter. Aggregate statistics
(mean makespan, correctness rate) and the ordering between paths are
stable across reruns; a handful of milliseconds of jitter on individual
rows is not.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, List, Optional

from saga_bench.config import FAILING_STEP
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import verify_rollback
from saga_bench.lease_store import LeaseStore
from saga_bench.paths.choreography import run_path_b
from saga_bench.paths.orchestration import run_path_a
from saga_bench.paths.path_d import run_path_d
from saga_bench.saga_store import SagaStore
from saga_bench.event_bus import EventBus
from saga_bench.experiment.scenario import build_scenario

PATHS = ("path_a", "path_b", "path_d", "path_d_lifo")


def run_single_saga(
    path: str,
    saga_id: str,
    extra_count: int,
    event_log: EventLog,
    saga_store: SagaStore,
    lease_store: LeaseStore,
) -> dict:
    """SagaStore and LeaseStore are shared across a sweep on purpose (the
    concurrency sweep specifically needs one shared LeaseStore mutex to
    contend on). The EventBus is deliberately NOT shared: Path B's
    dispatcher publishes onto a saga_id-scoped topic, so a per-saga
    EventBus is behaviorally identical to a shared one -- but sharing one
    bus's bounded thread pool across hundreds of concurrently-running
    sagas in a sweep would queue unrelated sagas' compensations behind
    each other and inflate makespan with an artifact of this benchmark's
    plumbing rather than anything about the coordination strategy itself.
    """
    services, step_order, graph = build_scenario(extra_count)
    fault_injector = FaultInjector(default_fail_step=FAILING_STEP)

    if path == "path_a":
        return run_path_a(saga_id, event_log, fault_injector, services=services, saga_store=saga_store, step_order=step_order)
    if path == "path_b":
        return run_path_b(
            saga_id, event_log, fault_injector, services=services, saga_store=saga_store, step_order=step_order, bus=EventBus()
        )
    if path == "path_d":
        return run_path_d(
            saga_id,
            event_log,
            fault_injector,
            services=services,
            saga_store=saga_store,
            lease_store=lease_store,
            step_order=step_order,
            graph=graph,
            scheduler="dependency_aware",
        )
    if path == "path_d_lifo":
        return run_path_d(
            saga_id,
            event_log,
            fault_injector,
            services=services,
            saga_store=saga_store,
            lease_store=lease_store,
            step_order=step_order,
            graph=graph,
            scheduler="lifo",
        )
    raise ValueError(f"unknown path {path!r}")


def _row_from_log(event_log: EventLog, saga_id: str, path: str, tags: dict) -> Optional[dict]:
    rows = event_log.rows_for(saga_id)
    by_event: Dict[str, float] = {}
    for r in rows:
        by_event.setdefault(r.event, r.timestamp_ms)

    if "failure_detected" not in by_event or "rollback_finished" not in by_event:
        return None  # saga succeeded (no fault configured) -- not a rollback data point

    makespan_ms = by_event["rollback_finished"] - by_event["failure_detected"]
    rollback_span_ms = by_event["rollback_finished"] - by_event.get("rollback_started", by_event["failure_detected"])

    overhead_ratio = 0.0
    if "elected_orchestrator" in by_event and rollback_span_ms > 0:
        overhead_ratio = (by_event["elected_orchestrator"] - by_event["rollback_started"]) / rollback_span_ms
        overhead_ratio = max(0.0, overhead_ratio)

    row = {
        "saga_id": saga_id,
        "path": path,
        "makespan_ms": makespan_ms,
        "correct": verify_rollback(event_log, saga_id),
        "coordination_overhead_ratio": overhead_ratio,
    }
    row.update(tags)
    return row


def run_width_sweep(
    executor: ThreadPoolExecutor,
    event_log: EventLog,
    widths=range(1, 9),
    instances_per=50,
    paths=("path_a", "path_b", "path_d"),
) -> List[dict]:
    saga_store = SagaStore()
    lease_store = LeaseStore()

    futures: Dict[Future, tuple] = {}
    for width in widths:
        for path in paths:
            for i in range(instances_per):
                saga_id = f"width-{width}-{path}-{i}-{uuid.uuid4().hex[:8]}"
                fut = executor.submit(run_single_saga, path, saga_id, width, event_log, saga_store, lease_store)
                futures[fut] = (path, saga_id, {"sweep": "dag_width", "width": width, "cluster_size": width + 4})

    rows = []
    for fut, (path, saga_id, tags) in futures.items():
        fut.result()
        row = _row_from_log(event_log, saga_id, path, tags)
        if row is not None:
            rows.append(row)
    return rows


def run_lifo_ablation_sweep(
    executor: ThreadPoolExecutor,
    event_log: EventLog,
    widths=range(1, 9),
    instances_per=20,
) -> List[dict]:
    saga_store = SagaStore()
    lease_store = LeaseStore()

    futures: Dict[Future, tuple] = {}
    for width in widths:
        for path in ("path_d", "path_d_lifo"):
            for i in range(instances_per):
                saga_id = f"ablation-{width}-{path}-{i}-{uuid.uuid4().hex[:8]}"
                fut = executor.submit(run_single_saga, path, saga_id, width, event_log, saga_store, lease_store)
                futures[fut] = (path, saga_id, {"sweep": "lifo_ablation", "width": width, "cluster_size": width + 4})

    rows = []
    for fut, (path, saga_id, tags) in futures.items():
        fut.result()
        row = _row_from_log(event_log, saga_id, path, tags)
        if row is not None:
            rows.append(row)
    return rows


def run_concurrency_sweep(
    executor: ThreadPoolExecutor,
    event_log: EventLog,
    concurrency_levels=range(1, 21),
    trials_per_level=1,
    width=1,
) -> List[dict]:
    """K simultaneous rollbacks sharing one LeaseStore (and thus its single
    global mutex) to see whether lease-acquisition contention shows up as
    coordination overhead as K grows.

    Each level's `trials_per_level * level` jobs are submitted together and
    all awaited before moving to the next level, so levels don't bleed into
    each other's concurrency count; within a level, everything really does
    run at once rather than being serialized wave by wave.
    """
    saga_store = SagaStore()
    lease_store = LeaseStore()

    rows: List[dict] = []
    for level in concurrency_levels:
        futures: Dict[Future, str] = {}
        for trial in range(trials_per_level):
            for k in range(level):
                saga_id = f"conc-{level}-{trial}-{k}-{uuid.uuid4().hex[:8]}"
                fut = executor.submit(
                    run_single_saga, "path_d", saga_id, width, event_log, saga_store, lease_store
                )
                futures[fut] = saga_id
        for fut, saga_id in futures.items():
            fut.result()
            row = _row_from_log(
                event_log,
                saga_id,
                "path_d",
                {"sweep": "concurrency", "concurrency_level": level, "width": width, "cluster_size": width + 4},
            )
            if row is not None:
                rows.append(row)
    return rows


def run_cluster_size_sweep(
    executor: ThreadPoolExecutor,
    event_log: EventLog,
    cluster_sizes=range(4, 17),
    instances_per=20,
    paths=("path_a", "path_b", "path_d"),
) -> List[dict]:
    """One cluster size's jobs are submitted and fully awaited before the
    next size starts. Coordination overhead is an election-time-over-total
    ratio measured in milliseconds; if every size's jobs were submitted at
    once (780 tasks racing for a shared, smaller worker pool, each also
    spawning its own nested election thread pool), a size-16 job could get
    its election timing inflated by unrelated queueing/thread-scheduling
    contention from size-4 jobs running at the same instant -- an artifact
    of this benchmark's own plumbing, not of cluster size. Isolating each
    size removes that confound.
    """
    saga_store = SagaStore()
    lease_store = LeaseStore()

    rows: List[dict] = []
    for size in cluster_sizes:
        extra_count = size - 4
        futures: Dict[Future, tuple] = {}
        for path in paths:
            for i in range(instances_per):
                saga_id = f"cluster-{size}-{path}-{i}-{uuid.uuid4().hex[:8]}"
                fut = executor.submit(
                    run_single_saga, path, saga_id, extra_count, event_log, saga_store, lease_store
                )
                futures[fut] = (path, saga_id, {"sweep": "cluster_size", "cluster_size": size, "width": extra_count})

        for fut, (path, saga_id, tags) in futures.items():
            fut.result()
            row = _row_from_log(event_log, saga_id, path, tags)
            if row is not None:
                rows.append(row)
    return rows


def run_all(max_workers: int = 64) -> tuple:
    """Runs every sweep against one shared thread pool. Returns
    (all_rows, master_event_log)."""
    event_log = EventLog()
    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        rows = []
        rows += run_width_sweep(executor, event_log)
        rows += run_lifo_ablation_sweep(executor, event_log)
        rows += run_concurrency_sweep(executor, event_log)
        rows += run_cluster_size_sweep(executor, event_log)

    elapsed_s = time.perf_counter() - start
    return rows, event_log, elapsed_s
