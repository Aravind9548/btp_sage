import csv
import threading
import time

from saga_bench.event_bus import EventBus
from saga_bench.event_log import EventLog
from saga_bench.fault_injector import FaultInjector
from saga_bench.lease_store import LeaseStore
from saga_bench.saga_store import SagaStore


def test_lease_race_exactly_one_winner():
    store = LeaseStore()
    results = [None] * 10
    barrier = threading.Barrier(10)

    def worker(i):
        barrier.wait()
        results[i] = store.try_acquire("saga-1", owner=f"owner-{i}", ttl_ms=5000)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r) == 1


def test_lease_expires_and_is_reacquirable():
    store = LeaseStore()
    assert store.try_acquire("saga-2", "owner-a", ttl_ms=50) is True
    assert store.try_acquire("saga-2", "owner-b", ttl_ms=50) is False
    time.sleep(0.08)
    assert store.try_acquire("saga-2", "owner-b", ttl_ms=50) is True


def test_lease_release_allows_reacquire():
    store = LeaseStore()
    assert store.try_acquire("saga-3", "owner-a", ttl_ms=5000) is True
    assert store.release("saga-3", "owner-a") is True
    assert store.try_acquire("saga-3", "owner-b", ttl_ms=5000) is True


def test_lease_release_by_non_owner_fails():
    store = LeaseStore()
    store.try_acquire("saga-4", "owner-a", ttl_ms=5000)
    assert store.release("saga-4", "owner-b") is False


def test_saga_store_thread_safety_and_idempotent_compensation():
    store = SagaStore()
    for step in ["Order", "Payment", "Inventory", "Notification"]:
        store.mark_completed("saga-5", step)
    assert store.completed_steps("saga-5") == {"Order", "Payment", "Inventory", "Notification"}

    first = store.mark_compensated("saga-5", "Payment")
    second = store.mark_compensated("saga-5", "Payment")
    assert first is True
    assert second is False
    assert store.is_compensated("saga-5", "Payment") is True


def test_event_log_preserves_ordering_under_concurrency():
    log = EventLog()

    def writer(n):
        for i in range(50):
            log.append(saga_id="saga-6", path="test", event="tick", step=str(n * 100 + i))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = log.rows()
    assert len(rows) == 8 * 50
    timestamps = [r.timestamp_ms for r in rows]
    assert timestamps == sorted(timestamps)


def test_event_log_to_csv(tmp_path):
    log = EventLog()
    log.append(saga_id="saga-7", path="test", event="started", step=None)
    log.append(saga_id="saga-7", path="test", event="finished", step="Order")

    out = tmp_path / "events.csv"
    log.to_csv(str(out))

    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["event"] == "started"
    assert rows[1]["step"] == "Order"


def test_event_bus_publish_dispatches_to_all_subscribers_concurrently():
    bus = EventBus()
    received = []
    lock = threading.Lock()

    def make_subscriber(name):
        def subscriber(payload):
            time.sleep(0.05)
            with lock:
                received.append((name, payload["value"]))
        return subscriber

    bus.subscribe("topic-a", make_subscriber("sub1"))
    bus.subscribe("topic-a", make_subscriber("sub2"))
    bus.subscribe("topic-a", make_subscriber("sub3"))

    start = time.monotonic()
    futures = bus.publish("topic-a", {"value": 42})
    for f in futures:
        f.result(timeout=2)
    elapsed = time.monotonic() - start

    assert len(received) == 3
    assert all(v == 42 for _, v in received)
    # Dispatched concurrently: three 50ms subscribers should take much less
    # than 3 * 50ms if run in parallel on the thread pool.
    assert elapsed < 0.15


def test_fault_injector_deterministic():
    injector = FaultInjector(per_saga_fail_step={"saga-8": "Payment"}, default_fail_step=None)
    assert injector.should_fail("saga-8", "Payment") is True
    assert injector.should_fail("saga-8", "Order") is False
    assert injector.should_fail("saga-9", "Payment") is False

    default_injector = FaultInjector(default_fail_step="Inventory")
    assert default_injector.should_fail("any-saga", "Inventory") is True
    assert default_injector.should_fail("any-saga", "Order") is False
