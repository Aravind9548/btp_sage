"""Single-saga, verbose walkthrough of Path D: choreography with on-demand
election and graph-aware compensation scheduling. Meant to be run live --
one command, no internet, finishes in well under 30 seconds.

Part 1 runs one saga end to end: forward execution, an injected failure,
the election race, and dependency-aware parallel compensation dispatch.
Part 2 stages an orchestrator crash mid-rollback to show lease expiry
triggering re-election, with no compensation ever run twice.
"""
from __future__ import annotations

import time

from saga_bench.config import FAILING_STEP
from saga_bench.event_bus import EventBus
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import default_graph, verify_rollback
from saga_bench.lease_store import LeaseStore
from saga_bench.paths.path_d import run_path_d
from saga_bench.saga_store import SagaStore
from saga_bench.services import build_services


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def narrate_log(event_log: EventLog, saga_id: str) -> None:
    rows = sorted(event_log.rows_for(saga_id), key=lambda r: r.timestamp_ms)
    for r in rows:
        step_part = f" [{r.step}]" if r.step else ""
        print(f"  t={r.timestamp_ms:8.1f}ms  {r.event}{step_part}")


def part_one() -> None:
    banner("PART 1: one saga, Path D end to end")
    saga_id = "demo-saga-1"
    event_log = EventLog()
    fault = FaultInjector(default_fail_step=FAILING_STEP)

    print(f"Saga {saga_id!r} will fail at step {FAILING_STEP!r} after Order, "
          f"Notification, and Payment have already completed.")
    print("Running...")

    result = run_path_d(saga_id, event_log, fault)

    print()
    print("Event timeline (compare compensate_finished[Payment] against")
    print("compensate_started[Notification] -- Payment must finish first):")
    narrate_log(event_log, saga_id)

    print()
    print(f"Elected orchestrator: {result['orchestrator']}")
    print(f"Completed steps:      {result['completed']}")
    print(f"Compensated steps:    {result['compensated']}")
    print(f"Rollback correct:     {verify_rollback(event_log, saga_id)}")


def part_two() -> None:
    banner("PART 2: orchestrator crash mid-rollback -> lease expiry -> re-election")
    saga_id = "demo-saga-2"
    event_log = EventLog()
    saga_store = SagaStore()
    lease_store = LeaseStore()
    services = build_services()
    graph = default_graph()

    completed = ["Order", "Notification", "Payment"]
    print(f"Forward phase: executing {completed} (Inventory will fail)...")
    for step in completed:
        services[step].execute(saga_id, "demo", event_log)
        saga_store.mark_completed(saga_id, step)
    print("Forward phase done.")

    print()
    print("orch-1 wins the lease (TTL=150ms) and compensates Payment, then crashes")
    print("(never renews, never releases)...")
    assert lease_store.try_acquire(saga_id, "orch-1", ttl_ms=150)
    services["Payment"].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    print("orch-1 has 'crashed'. Waiting for its lease to expire...")
    time.sleep(0.2)

    print()
    print("orch-2 re-acquires the now-expired lease and inspects SagaStore:")
    assert lease_store.try_acquire(saga_id, "orch-2", ttl_ms=2000)
    already_done = saga_store.compensated_steps(saga_id)
    remaining = set(completed) - already_done
    print(f"  already compensated (by orch-1): {sorted(already_done)}")
    print(f"  remaining for orch-2:            {sorted(remaining)}")

    ready = graph.subgraph(saga_store.completed_steps(saga_id)).ready_steps(remaining, finished=already_done)
    print(f"  ready to dispatch now (Payment already finished, so Notification")
    print(f"  is unblocked): {sorted(ready)}")
    for step in ready:
        services[step].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    lease_store.release(saga_id, "orch-2")

    print()
    print("Final state:")
    print(f"  compensated steps: {sorted(saga_store.compensated_steps(saga_id))}")
    print(f"  rollback correct:  {verify_rollback(event_log, saga_id)}")

    starts = [r.step for r in event_log.rows_for(saga_id) if r.event == "compensate_started"]
    print(f"  compensate_started events: {starts}  (each step exactly once -> no duplicate compensation)")

    # Prove idempotency explicitly: orch-1 "waking up" and retrying is a no-op.
    ran_again = services["Payment"].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    print(f"  orch-1 belatedly retries Payment's compensation -> ran again? {ran_again} (must be False)")


def main() -> None:
    start = time.perf_counter()
    part_one()
    part_two()
    banner(f"Demo finished in {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    main()
