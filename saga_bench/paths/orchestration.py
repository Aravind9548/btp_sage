"""Path A: orchestration baseline.

A single coordinator function calls services in sequence and stops the
first time a step is configured to fail (see fault_injector.py). If any
step never got to run, the coordinator then runs compensations for
whatever *did* complete, in strict reverse of the forward order, one at a
time. This is deliberately not built on any cloud workflow service (e.g.
Step Functions) -- a plain sequential coordinator has identical semantics
for what this benchmark measures: correctness (given the hand-picked
STEP_ORDER, see config.py), at the cost of fully serialized compensation.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from saga_bench.config import STEP_ORDER
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.saga_store import SagaStore
from saga_bench.services import Service, build_services

PATH_NAME = "path_a_orchestration"


def run_path_a(
    saga_id: str,
    event_log: EventLog,
    fault_injector: FaultInjector,
    services: Optional[Dict[str, Service]] = None,
    saga_store: Optional[SagaStore] = None,
    step_order: Sequence[str] = STEP_ORDER,
) -> dict:
    if services is None:
        services = build_services()
    if saga_store is None:
        saga_store = SagaStore()

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
    compensated: List[str] = []
    for step in reversed(completed):
        ran = services[step].compensate(saga_id, PATH_NAME, event_log, saga_store=saga_store)
        if ran:
            compensated.append(step)
    event_log.append(saga_id, PATH_NAME, "rollback_finished")

    return {
        "saga_id": saga_id,
        "failed": True,
        "failed_step": failed_step,
        "completed": completed,
        "compensated": compensated,
    }
