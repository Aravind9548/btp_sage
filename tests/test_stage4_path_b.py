from saga_bench.config import SERVICES
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import verify_rollback
from saga_bench.paths.choreography import run_path_b


def test_path_b_makespan_is_close_to_max_not_sum():
    # Fail at Inventory so Order, Notification, and Payment all completed
    # and all three react to CompensationNeeded concurrently.
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    result = run_path_b("saga-b1", log, fault)

    assert result["completed"] == ["Order", "Notification", "Payment"]
    assert set(result["compensated"]) == {"Order", "Notification", "Payment"}

    max_compensate_ms = max(
        SERVICES["Order"].compensate_ms, SERVICES["Notification"].compensate_ms, SERVICES["Payment"].compensate_ms
    )  # Payment: 800ms
    sum_compensate_ms = (
        SERVICES["Order"].compensate_ms + SERVICES["Notification"].compensate_ms + SERVICES["Payment"].compensate_ms
    )  # 1050ms

    rows = log.rows_for("saga-b1")
    rollback_started_ms = next(r.timestamp_ms for r in rows if r.event == "rollback_started")
    rollback_finished_ms = next(r.timestamp_ms for r in rows if r.event == "rollback_finished")
    rollback_elapsed_ms = rollback_finished_ms - rollback_started_ms

    assert rollback_elapsed_ms < sum_compensate_ms * 0.8
    assert max_compensate_ms * 0.7 <= rollback_elapsed_ms <= max_compensate_ms * 1.5


def test_path_b_violates_ordering_constraint():
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    result = run_path_b("saga-b2", log, fault)

    assert result["failed"] is True
    # Notification's compensation (100ms) finishes long before Payment's
    # (800ms) even though the graph requires the opposite ordering -- this
    # is the intended failure mode of naive choreography, not a bug.
    assert verify_rollback(log, "saga-b2") is False
