"""Path B: choreography baseline.

Each service reacts to the previous service's success event and executes
its own step -- there is no coordinator. On failure, a single
`CompensationNeeded` event is published and every service that completed a
step reacts independently and immediately, running its own compensation
concurrently with every other one.

Critical instruction from the spec: do not make this path correct. Path B
has no coordinator and therefore no knowledge of the dependency graph. It
must be able to send the cancellation notice before the refund has
completed -- that is the experimental result being measured, not a bug.
No ordering logic, waits, or graph awareness are added here.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from saga_bench.config import STEP_ORDER
from saga_bench.event_bus import EventBus
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.saga_store import SagaStore
from saga_bench.services import Service, build_services

PATH_NAME = "path_b_choreography"


def run_path_b(
    saga_id: str,
    event_log: EventLog,
    fault_injector: FaultInjector,
    services: Optional[Dict[str, Service]] = None,
    saga_store: Optional[SagaStore] = None,
    step_order: Sequence[str] = STEP_ORDER,
    bus: Optional[EventBus] = None,
) -> dict:
    if services is None:
        services = build_services()
    if saga_store is None:
        saga_store = SagaStore()
    if bus is None:
        bus = EventBus()

    event_log.append(saga_id, PATH_NAME, "saga_started")

    completed: List[str] = []
    failed_step: Optional[str] = None

    # Choreographed "chain of custody": each step reacts to the previous
    # step's success by running its own step. Implemented here as a plain
    # loop for determinism (no cross-service scheduling ambiguity in the
    # happy path), which is behaviorally identical to a bus-driven chain
    # since each step only ever depends on the one immediately before it.
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

    # Every completed step's service subscribes to CompensationNeeded and
    # reacts on its own -- no coordinator, no knowledge of other steps, no
    # ordering. All dispatched onto the bus's thread pool so they truly run
    # concurrently with respect to each other.
    ran_flags: Dict[str, bool] = {}

    def make_reactor(step_name: str):
        def reactor(_payload: dict) -> None:
            ran_flags[step_name] = services[step_name].compensate(
                saga_id, PATH_NAME, event_log, saga_store=saga_store
            )
        return reactor

    for step in completed:
        bus.subscribe(f"CompensationNeeded:{saga_id}", make_reactor(step))

    event_log.append(saga_id, PATH_NAME, "rollback_started")
    futures = bus.publish(f"CompensationNeeded:{saga_id}", {"saga_id": saga_id, "failed_step": failed_step})
    for f in futures:
        f.result()
    event_log.append(saga_id, PATH_NAME, "rollback_finished")

    compensated = [step for step in completed if ran_flags.get(step)]

    return {
        "saga_id": saga_id,
        "failed": True,
        "failed_step": failed_step,
        "completed": completed,
        "compensated": compensated,
    }
