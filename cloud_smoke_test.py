"""Quick health check: is LocalStack running? Do the DynamoDB tables exist?

Usage:
    python cloud_smoke_test.py
"""
from __future__ import annotations

import sys
import urllib.request
import urllib.error

from cloud.config import (
    EVENT_LOG_TABLE,
    LEASE_TABLE,
    LOCALSTACK_ENDPOINT,
    SAGA_STATE_TABLE,
    get_client,
)


def check_localstack() -> bool:
    try:
        r = urllib.request.urlopen(
            f"{LOCALSTACK_ENDPOINT}/_localstack/health", timeout=3
        )
        if r.status == 200:
            print("[PASS] LocalStack is running")
            return True
        print(f"[FAIL] LocalStack returned status {r.status}")
        return False
    except (urllib.error.URLError, OSError):
        print("[FAIL] LocalStack is not reachable at", LOCALSTACK_ENDPOINT)
        print("       Start it with: docker-compose -f cloud/setup/docker-compose.yml up -d")
        return False


def check_table(table_name: str) -> bool:
    dynamodb = get_client("dynamodb")
    try:
        resp = dynamodb.describe_table(TableName=table_name)
        status = resp["Table"]["TableStatus"]
        print(f"[PASS] Table {table_name} exists (status: {status})")
        return True
    except Exception as e:
        print(f"[FAIL] Table {table_name} not found: {e}")
        print(f"       Run: python -m cloud.setup.create_resources")
        return False


def main() -> None:
    print("Cloud smoke test")
    print("=" * 50)

    results = []
    results.append(check_localstack())

    if results[0]:
        for table in [LEASE_TABLE, SAGA_STATE_TABLE, EVENT_LOG_TABLE]:
            results.append(check_table(table))

    print()
    if all(results):
        print("All checks passed. Ready to run: python cloud_demo.py")
        sys.exit(0)
    else:
        print("Some checks failed. See above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
