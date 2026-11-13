import time

from saga_bench.config import SERVICES, STEP_ORDER
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import verify_rollback
from saga_bench.paths.orchestration import run_path_a


def test_path_a_payment_failure_rolls_back_completed_steps_sequentially():
    # STEP_ORDER is Order, Notification, Payment, Inventory. A Payment
    # failure means the coordinator stops before Payment ever runs, so only
    # Order and Notification (already executed) need compensating.
    log = EventLog()
    fault = FaultInjector(default_fail_step="Payment")

    start = time.perf_counter()
    result = run_path_a("saga-a1", log, fault)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert result["failed"] is True
    assert result["failed_step"] == "Payment"
    assert result["completed"] == ["Order", "Notification"]
    assert set(result["compensated"]) == {"Order", "Notification"}

    total_execute_ms = SERVICES["Order"].execute_ms + SERVICES["Notification"].execute_ms
    total_compensate_ms = SERVICES["Order"].compensate_ms + SERVICES["Notification"].compensate_ms
    expected_ms = total_execute_ms + total_compensate_ms

    # Sequential coordinator: total wall time tracks the sum of durations,
    # not the max -- with generous slack for scheduling jitter.
    assert expected_ms * 0.7 <= elapsed_ms <= expected_ms * 2.0

    assert verify_rollback(log, "saga-a1") is True


def test_path_a_inventory_failure_exercises_the_dependency_edge():
    # Fail at Inventory (last step) so Order, Notification, AND Payment all
    # complete -- this is the scenario that actually exercises the
    # Payment-before-Notification constraint, since both ends are present.
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    result = run_path_a("saga-a3", log, fault)

    assert result["completed"] == ["Order", "Notification", "Payment"]
    assert set(result["compensated"]) == {"Order", "Notification", "Payment"}
    assert verify_rollback(log, "saga-a3") is True


def test_path_a_success_when_no_fault_configured():
    log = EventLog()
    fault = FaultInjector()  # no fault configured -> saga succeeds

    result = run_path_a("saga-a2", log, fault)

    assert result["failed"] is False
    assert result["completed"] == list(STEP_ORDER)
    assert result["compensated"] == []
    events = [r.event for r in log.rows_for("saga-a2")]
    assert "saga_succeeded" in events
    assert "rollback_started" not in events
