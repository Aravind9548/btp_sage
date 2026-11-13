from saga_bench.config import SERVICES
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import default_graph, verify_rollback
from saga_bench.lease_store import LeaseStore
from saga_bench.paths.path_d import run_path_d
from saga_bench.saga_store import SagaStore
from saga_bench.services import build_services

SUM_MS = SERVICES["Order"].compensate_ms + SERVICES["Notification"].compensate_ms + SERVICES["Payment"].compensate_ms  # 1050
MAX_MS = max(SERVICES["Order"].compensate_ms, SERVICES["Notification"].compensate_ms, SERVICES["Payment"].compensate_ms)  # 800
CRITICAL_PATH_MS = SERVICES["Payment"].compensate_ms + SERVICES["Notification"].compensate_ms  # 900, Order(150) is shorter


def _rollback_elapsed_ms(log: EventLog, saga_id: str) -> float:
    rows = log.rows_for(saga_id)
    started = next(r.timestamp_ms for r in rows if r.event == "rollback_started")
    finished = next(r.timestamp_ms for r in rows if r.event == "rollback_finished")
    return finished - started


def test_path_d_makespan_between_path_b_max_and_path_a_sum():
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    result = run_path_d("saga-d1", log, fault)

    assert result["completed"] == ["Order", "Notification", "Payment"]
    assert set(result["compensated"]) == {"Order", "Notification", "Payment"}

    elapsed = _rollback_elapsed_ms(log, "saga-d1")
    assert elapsed < SUM_MS * 0.95  # noticeably less than Path A's fully sequential sum
    assert MAX_MS * 0.9 <= elapsed <= CRITICAL_PATH_MS * 1.5  # roughly the critical path, slightly above raw max


def test_path_d_verify_rollback_true_on_every_run():
    for i in range(10):
        log = EventLog()
        fault = FaultInjector(default_fail_step="Inventory")
        run_path_d(f"saga-d-loop-{i}", log, fault)
        assert verify_rollback(log, f"saga-d-loop-{i}") is True


def test_path_d_election_picks_exactly_one_orchestrator():
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    run_path_d("saga-d2", log, fault)

    elected_events = [r for r in log.rows_for("saga-d2") if r.event == "elected_orchestrator"]
    assert len(elected_events) == 1


def test_path_d_lifo_ablation_is_correct_but_slow_like_path_a():
    log = EventLog()
    fault = FaultInjector(default_fail_step="Inventory")

    result = run_path_d("saga-d3", log, fault, scheduler="lifo")

    assert set(result["compensated"]) == {"Order", "Notification", "Payment"}
    assert verify_rollback(log, "saga-d3") is True

    elapsed = _rollback_elapsed_ms(log, "saga-d3")
    # LIFO ignores the graph and never parallelizes -- it should behave like
    # Path A's sequential sum, not the dependency-aware scheduler's
    # near-critical-path time.
    assert elapsed >= SUM_MS * 0.7


def test_path_d_recovers_after_orchestrator_crash_mid_rollback():
    """Simulates killing the elected orchestrator mid-rollback: orchestrator
    1 compensates a single step then "crashes" (never renews or releases
    its lease). Once the short TTL expires, orchestrator 2 re-acquires the
    lease, sees SagaStore's compensated-steps marker, and only compensates
    what remains -- proving no compensation runs twice.
    """
    saga_id = "saga-d-crash"
    log = EventLog()
    saga_store = SagaStore()
    lease_store = LeaseStore()
    services = build_services()
    graph = default_graph()

    completed = ["Order", "Notification", "Payment"]
    for step in completed:
        services[step].execute(saga_id, "path_d", log)
        saga_store.mark_completed(saga_id, step)

    # Orchestrator 1 wins a short-TTL lease and compensates only Payment
    # (the one step with no predecessor in the sub-graph), then "crashes".
    assert lease_store.try_acquire(saga_id, "orch-1", ttl_ms=80) is True
    ran1 = services["Payment"].compensate(saga_id, "path_d", log, saga_store=saga_store)
    assert ran1 is True

    # orch-1 never releases or renews -> wait for TTL to expire.
    import time

    time.sleep(0.12)

    # Orchestrator 2 re-acquires and finishes the remaining work.
    assert lease_store.try_acquire(saga_id, "orch-2", ttl_ms=2000) is True
    remaining = set(completed) - saga_store.compensated_steps(saga_id)
    assert remaining == {"Order", "Notification"}

    sub_graph = graph.subgraph(saga_store.completed_steps(saga_id))
    # Dependency-aware dispatch of just what's left: Notification depends
    # on Payment, which is already compensated (finished), so it is ready
    # immediately alongside Order.
    ready = sub_graph.ready_steps(remaining, finished=saga_store.compensated_steps(saga_id))
    assert ready == {"Order", "Notification"}
    for step in ready:
        services[step].compensate(saga_id, "path_d", log, saga_store=saga_store)

    assert saga_store.compensated_steps(saga_id) == {"Order", "Notification", "Payment"}
    assert verify_rollback(log, saga_id) is True

    # No compensation ran twice: exactly one compensate_started per step.
    starts = [r for r in log.rows_for(saga_id) if r.event == "compensate_started"]
    steps_started = [r.step for r in starts]
    assert sorted(steps_started) == sorted(completed)
    assert len(steps_started) == len(set(steps_started))

    # A duplicate attempt by orch-1 (if it somehow woke back up) must be a
    # no-op thanks to the idempotency marker.
    ran_again = services["Payment"].compensate(saga_id, "path_d", log, saga_store=saga_store)
    assert ran_again is False
