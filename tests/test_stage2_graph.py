from saga_bench.config import SERVICES, STEP_ORDER
from saga_bench.event_log import EventLog
from saga_bench.graph import default_graph, verify_rollback
from saga_bench.saga_store import SagaStore
from saga_bench.services import Service


def test_default_graph_topological_order_respects_edges():
    graph = default_graph()
    order = graph.topological_order()
    assert order.index("Payment") < order.index("Notification")
    assert set(order) == set(STEP_ORDER)


def test_critical_path_length_accounts_for_dependency():
    graph = default_graph()
    durations = {name: spec.compensate_ms for name, spec in SERVICES.items()}
    cpl = graph.critical_path_length(durations)
    # Payment(800) -> Notification(100) is the longest chain; Order(150) and
    # Inventory(200) are independent and shorter than that chain alone.
    assert cpl == 900


def test_ready_steps_only_after_predecessors_finished():
    graph = default_graph()
    remaining = {"Order", "Payment", "Inventory", "Notification"}
    ready = graph.ready_steps(remaining, finished=set())
    assert "Notification" not in ready
    assert {"Order", "Payment", "Inventory"} <= ready

    ready_after_payment = graph.ready_steps({"Notification"}, finished={"Payment"})
    assert ready_after_payment == {"Notification"}


def test_subgraph_only_keeps_edges_between_retained_nodes():
    graph = default_graph()
    sub = graph.subgraph({"Order", "Inventory"})
    assert sub.edges == []

    sub_with_edge = graph.subgraph({"Payment", "Notification"})
    assert sub_with_edge.edges == [("Payment", "Notification")]


def test_verify_rollback_false_when_notification_precedes_refund():
    log = EventLog()
    saga_id = "bad-saga"
    # Hand-construct an out-of-order timeline: notification fully finishes
    # (t=0..10) before payment's refund even starts (t=20..40).
    log.append(saga_id, "path-b", "compensate_started", "Notification", timestamp_ms=0)
    log.append(saga_id, "path-b", "compensate_finished", "Notification", timestamp_ms=10)
    log.append(saga_id, "path-b", "compensate_started", "Payment", timestamp_ms=20)
    log.append(saga_id, "path-b", "compensate_finished", "Payment", timestamp_ms=40)

    assert verify_rollback(log, saga_id) is False


def test_verify_rollback_true_for_valid_ordering():
    log = EventLog()
    saga_id = "good-saga"
    log.append(saga_id, "path-a", "compensate_started", "Payment", timestamp_ms=0)
    log.append(saga_id, "path-a", "compensate_finished", "Payment", timestamp_ms=20)
    log.append(saga_id, "path-a", "compensate_started", "Notification", timestamp_ms=20)
    log.append(saga_id, "path-a", "compensate_finished", "Notification", timestamp_ms=30)

    assert verify_rollback(log, saga_id) is True


def test_verify_rollback_true_when_notification_not_needed():
    log = EventLog()
    saga_id = "partial-saga"
    log.append(saga_id, "path-a", "compensate_started", "Order", timestamp_ms=0)
    log.append(saga_id, "path-a", "compensate_finished", "Order", timestamp_ms=10)
    assert verify_rollback(log, saga_id) is True


def test_service_execute_and_compensate_emit_expected_events():
    log = EventLog()
    saga_store = SagaStore()
    service = Service(SERVICES["Order"])

    service.execute("saga-x", "test", log)
    ran = service.compensate("saga-x", "test", log, saga_store=saga_store)
    assert ran is True

    events = [(r.event, r.step) for r in log.rows_for("saga-x")]
    assert events == [
        ("execute_started", "Order"),
        ("execute_finished", "Order"),
        ("compensate_started", "Order"),
        ("compensate_finished", "Order"),
    ]

    # Idempotent: a second compensate() for the same saga/step is skipped.
    ran_again = service.compensate("saga-x", "test", log, saga_store=saga_store)
    assert ran_again is False
    assert log.rows_for("saga-x")[-1].event == "compensate_skipped_duplicate"
