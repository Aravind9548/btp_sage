"""Cloud demo: same walkthrough as demo.py but with DynamoDB-backed stores.

Runs against LocalStack -- start it first with:
    docker-compose -f cloud/setup/docker-compose.yml up -d
    python -m cloud.setup.create_resources

Then run:
    python cloud_demo.py

All state (leases, saga progress, event logs) is written to real DynamoDB
tables, demonstrating that the saga_bench architecture maps directly to
AWS services. Services still run locally (they just sleep) -- the cloud
value is in the coordination and state infrastructure.
"""
from __future__ import annotations

import time

from cloud.dynamo_event_log import DynamoEventLog
from cloud.dynamo_lease_store import DynamoLeaseStore
from cloud.dynamo_saga_store import DynamoSagaStore
from cloud.config import get_client, LEASE_TABLE, SAGA_STATE_TABLE, EVENT_LOG_TABLE
from saga_bench.config import FAILING_STEP
from saga_bench.fault_injector import FaultInjector
from saga_bench.graph import default_graph, verify_rollback
from saga_bench.paths.orchestration import run_path_a
from saga_bench.paths.choreography import run_path_b
from saga_bench.paths.path_d import run_path_d
from saga_bench.services import build_services


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def narrate_log(event_log: DynamoEventLog, saga_id: str) -> None:
    rows = sorted(event_log.rows_for(saga_id), key=lambda r: r.timestamp_ms)
    for r in rows:
        step_part = f" [{r.step}]" if r.step else ""
        print(f"  t={r.timestamp_ms:8.1f}ms  {r.event}{step_part}")


def show_dynamodb_state(saga_id: str) -> None:
    """Scan DynamoDB tables to show real cloud state."""
    dynamodb = get_client("dynamodb")
    print()
    print("  --- DynamoDB state ---")

    # SagaState
    resp = dynamodb.get_item(
        TableName=SAGA_STATE_TABLE,
        Key={"saga_id": {"S": saga_id}},
    )
    item = resp.get("Item", {})
    completed = sorted(item.get("completed_steps", {}).get("SS", []))
    compensated = sorted(item.get("compensated_steps", {}).get("SS", []))
    print(f"  SagaState[{saga_id}]: completed={completed}, compensated={compensated}")

    # SagaLeases
    resp = dynamodb.get_item(
        TableName=LEASE_TABLE,
        Key={"saga_id": {"S": saga_id}},
    )
    lease_item = resp.get("Item")
    if lease_item:
        owner = lease_item.get("owner", {}).get("S", "?")
        expires = lease_item.get("expires_at_epoch_ms", {}).get("N", "?")
        print(f"  SagaLeases[{saga_id}]: owner={owner}, expires_at_epoch_ms={expires}")
    else:
        print(f"  SagaLeases[{saga_id}]: (released / no lease)")

    # EventLog count
    resp = dynamodb.query(
        TableName=EVENT_LOG_TABLE,
        KeyConditionExpression="saga_id = :sid",
        ExpressionAttributeValues={":sid": {"S": saga_id}},
        Select="COUNT",
    )
    print(f"  EventLog[{saga_id}]: {resp['Count']} events recorded")


def clear_tables() -> None:
    """Delete all items from all tables for a clean demo run."""
    dynamodb = get_client("dynamodb")
    for table_name, key_schema in [
        (SAGA_STATE_TABLE, ["saga_id"]),
        (LEASE_TABLE, ["saga_id"]),
        (EVENT_LOG_TABLE, ["saga_id", "timestamp_ms"]),
    ]:
        resp = dynamodb.scan(TableName=table_name)
        for item in resp.get("Items", []):
            key = {}
            for k in key_schema:
                key[k] = item[k]
            dynamodb.delete_item(TableName=table_name, Key=key)


def part_one_path_d() -> None:
    banner("PART 1: Path D (election + graph-aware scheduling) on DynamoDB")
    saga_id = "cloud-demo-1"
    event_log = DynamoEventLog()
    saga_store = DynamoSagaStore()
    lease_store = DynamoLeaseStore()
    fault = FaultInjector(default_fail_step=FAILING_STEP)
    services = build_services()
    graph = default_graph()

    print(f"Saga {saga_id!r} will fail at step {FAILING_STEP!r}.")
    print("All state is written to DynamoDB in LocalStack.")
    print("Running...")

    result = run_path_d(
        saga_id, event_log, fault,
        services=services,
        saga_store=saga_store,
        lease_store=lease_store,
        graph=graph,
    )

    print()
    print("Event timeline (from DynamoDB EventLog table):")
    narrate_log(event_log, saga_id)

    print()
    print(f"Elected orchestrator: {result['orchestrator']}")
    print(f"Completed steps:      {result['completed']}")
    print(f"Compensated steps:    {result['compensated']}")
    print(f"Rollback correct:     {verify_rollback(event_log, saga_id)}")

    show_dynamodb_state(saga_id)


def part_two_crash_recovery() -> None:
    banner("PART 2: Orchestrator crash + re-election on DynamoDB")
    saga_id = "cloud-demo-2"
    event_log = DynamoEventLog()
    saga_store = DynamoSagaStore()
    lease_store = DynamoLeaseStore()
    services = build_services()
    graph = default_graph()

    completed = ["Order", "Notification", "Payment"]
    print(f"Forward phase: executing {completed} (Inventory will fail)...")
    for step in completed:
        services[step].execute(saga_id, "demo", event_log)
        saga_store.mark_completed(saga_id, step)
    print("Forward phase done. State persisted to DynamoDB.")

    print()
    print("orch-1 wins the lease (TTL=150ms) and compensates Payment, then crashes...")
    assert lease_store.try_acquire(saga_id, "orch-1", ttl_ms=150)
    services["Payment"].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    print("orch-1 has 'crashed'. Waiting for its DynamoDB lease to expire...")
    time.sleep(0.2)

    print()
    print("orch-2 re-acquires the now-expired lease and reads SagaStore from DynamoDB:")
    assert lease_store.try_acquire(saga_id, "orch-2", ttl_ms=2000)
    already_done = saga_store.compensated_steps(saga_id)
    remaining = set(completed) - already_done
    print(f"  already compensated (by orch-1): {sorted(already_done)}")
    print(f"  remaining for orch-2:            {sorted(remaining)}")

    ready = graph.subgraph(saga_store.completed_steps(saga_id)).ready_steps(
        remaining, finished=already_done
    )
    print(f"  ready to dispatch now: {sorted(ready)}")
    for step in ready:
        services[step].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    lease_store.release(saga_id, "orch-2")

    print()
    print("Final state (from DynamoDB):")
    print(f"  compensated steps: {sorted(saga_store.compensated_steps(saga_id))}")
    print(f"  rollback correct:  {verify_rollback(event_log, saga_id)}")

    ran_again = services["Payment"].compensate(saga_id, "demo", event_log, saga_store=saga_store)
    print(f"  orch-1 belatedly retries Payment -> ran again? {ran_again} (must be False)")

    show_dynamodb_state(saga_id)


def part_three_path_a() -> None:
    banner("PART 3: Path A (orchestration baseline) on DynamoDB")
    saga_id = "cloud-demo-3"
    event_log = DynamoEventLog()
    saga_store = DynamoSagaStore()
    fault = FaultInjector(default_fail_step=FAILING_STEP)
    services = build_services()

    print(f"Running sequential orchestration (Path A)...")

    result = run_path_a(
        saga_id, event_log, fault,
        services=services,
        saga_store=saga_store,
    )

    print(f"Completed steps: {result['completed']}")
    print(f"Compensated:     {result['compensated']}")
    print(f"Rollback correct: {verify_rollback(event_log, saga_id)}")
    show_dynamodb_state(saga_id)


def part_four_path_b() -> None:
    banner("PART 4: Path B (choreography baseline) on DynamoDB")
    saga_id = "cloud-demo-4"
    event_log = DynamoEventLog()
    saga_store = DynamoSagaStore()
    fault = FaultInjector(default_fail_step=FAILING_STEP)
    services = build_services()

    print("Running naive choreography (Path B) -- expects ordering violation...")

    result = run_path_b(
        saga_id, event_log, fault,
        services=services,
        saga_store=saga_store,
    )

    correct = verify_rollback(event_log, saga_id)
    print(f"Completed steps: {result['completed']}")
    print(f"Compensated:     {result['compensated']}")
    print(f"Rollback correct: {correct}  (expected: False -- choreography has no ordering)")
    show_dynamodb_state(saga_id)


def part_five_kafka() -> None:
    banner("PART 5: Path B with Kafka EventBus (instead of SNS/SQS)")
    try:
        from cloud.kafka_event_bus import KafkaEventBus
    except ImportError:
        print("  kafka-python-ng not installed. Skipping.")
        print("  Install with: pip install kafka-python-ng")
        return

    saga_id = "cloud-demo-5-kafka"
    event_log = DynamoEventLog()
    saga_store = DynamoSagaStore()
    fault = FaultInjector(default_fail_step=FAILING_STEP)
    services = build_services()

    print("Running Path B with Kafka as the event bus...")
    print("(Kafka topics auto-created on first publish)")

    try:
        kafka_bus = KafkaEventBus(bootstrap_servers="localhost:9092")
    except Exception as e:
        print(f"  Could not connect to Kafka: {e}")
        print("  Make sure Kafka is running:")
        print("    docker-compose -f cloud/setup/docker-compose.yml up -d")
        return

    try:
        result = run_path_b(
            saga_id, event_log, fault,
            services=services,
            saga_store=saga_store,
            bus=kafka_bus,
        )
        correct = verify_rollback(event_log, saga_id)
        print(f"Completed steps: {result['completed']}")
        print(f"Compensated:     {result['compensated']}")
        print(f"Rollback correct: {correct}  (expected: False)")
        show_dynamodb_state(saga_id)
    finally:
        kafka_bus.shutdown()


def main() -> None:
    start = time.perf_counter()

    print("Clearing DynamoDB tables for a clean run...")
    clear_tables()

    part_one_path_d()
    part_two_crash_recovery()
    part_three_path_a()
    part_four_path_b()
    part_five_kafka()

    banner(f"Cloud demo finished in {time.perf_counter() - start:.2f}s")
    print()
    print("All state was written to and read from DynamoDB in LocalStack.")
    print("Kafka was used as event bus in Part 5 (industry-standard messaging).")
    print("The same code would work against real AWS / Confluent Cloud with only")
    print("endpoint/bootstrap changes.")


if __name__ == "__main__":
    main()
