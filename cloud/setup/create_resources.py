"""Create all DynamoDB tables and SNS topics in LocalStack.

Idempotent: safe to run multiple times (catches ResourceInUseException).
Run after every LocalStack restart -- the free Hobby tier does not persist
IAM, SNS, or SQS resources across restarts.

Usage:
    python -m cloud.setup.create_resources
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cloud.config import (
    EVENT_LOG_TABLE,
    LEASE_TABLE,
    SAGA_STATE_TABLE,
    get_client,
)


def _create_table(dynamodb, table_name: str, key_schema: list, attr_defs: list) -> None:
    try:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=key_schema,
            AttributeDefinitions=attr_defs,
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"  [OK] Created table {table_name}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"  [--] Table {table_name} already exists")


def create_tables() -> None:
    dynamodb = get_client("dynamodb")

    _create_table(
        dynamodb,
        LEASE_TABLE,
        key_schema=[{"AttributeName": "saga_id", "KeyType": "HASH"}],
        attr_defs=[{"AttributeName": "saga_id", "AttributeType": "S"}],
    )

    _create_table(
        dynamodb,
        SAGA_STATE_TABLE,
        key_schema=[{"AttributeName": "saga_id", "KeyType": "HASH"}],
        attr_defs=[{"AttributeName": "saga_id", "AttributeType": "S"}],
    )

    _create_table(
        dynamodb,
        EVENT_LOG_TABLE,
        key_schema=[
            {"AttributeName": "saga_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp_ms", "KeyType": "RANGE"},
        ],
        attr_defs=[
            {"AttributeName": "saga_id", "AttributeType": "S"},
            {"AttributeName": "timestamp_ms", "AttributeType": "N"},
        ],
    )


def create_sns_topics() -> None:
    sns = get_client("sns")
    try:
        sns.create_topic(Name="saga-CompensationNeeded")
        print("  [OK] Created SNS topic saga-CompensationNeeded")
    except Exception:
        print("  [--] SNS topic saga-CompensationNeeded already exists or could not be created")


def main() -> None:
    print("Creating DynamoDB tables...")
    create_tables()
    print("Creating SNS topics...")
    create_sns_topics()
    print("Done.")


if __name__ == "__main__":
    main()
