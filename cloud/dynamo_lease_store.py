"""DynamoDB-backed LeaseStore -- drop-in replacement for saga_bench.lease_store.LeaseStore.

Table: SagaLeases
  PK: saga_id (S)
  Attributes: owner (S), expires_at_epoch_ms (N)

try_acquire uses a ConditionExpression equivalent to DynamoDB's
`attribute_not_exists(saga_id)` -- the exact mechanism modelled by the
in-memory LeaseStore. LocalStack's free Hobby tier does NOT auto-reap
TTL items, so every read explicitly checks expires_at_epoch_ms.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional

from botocore.exceptions import ClientError

from cloud.config import LEASE_TABLE, get_resource


def _now_ms() -> int:
    return int(time.time() * 1000)


class DynamoLeaseStore:
    def __init__(
        self,
        table_name: str = LEASE_TABLE,
        endpoint_url: str | None = None,
    ) -> None:
        resource = get_resource("dynamodb") if endpoint_url is None else get_resource("dynamodb", endpoint_url)
        self._table = resource.Table(table_name)

    def try_acquire(self, saga_id: str, owner: str, ttl_ms: float = 2000.0) -> bool:
        now = _now_ms()
        expires = now + int(ttl_ms)
        try:
            self._table.put_item(
                Item={
                    "saga_id": saga_id,
                    "owner": owner,
                    "expires_at_epoch_ms": Decimal(str(expires)),
                },
                ConditionExpression=(
                    "attribute_not_exists(saga_id) OR expires_at_epoch_ms < :now"
                ),
                ExpressionAttributeValues={":now": Decimal(str(now))},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def renew(self, saga_id: str, owner: str, ttl_ms: float = 2000.0) -> bool:
        now = _now_ms()
        expires = now + int(ttl_ms)
        try:
            self._table.update_item(
                Key={"saga_id": saga_id},
                UpdateExpression="SET expires_at_epoch_ms = :expires",
                ConditionExpression="#o = :owner AND expires_at_epoch_ms > :now",
                ExpressionAttributeNames={"#o": "owner"},
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":now": Decimal(str(now)),
                    ":expires": Decimal(str(expires)),
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def release(self, saga_id: str, owner: str) -> bool:
        try:
            self._table.delete_item(
                Key={"saga_id": saga_id},
                ConditionExpression="#o = :owner",
                ExpressionAttributeNames={"#o": "owner"},
                ExpressionAttributeValues={":owner": owner},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def current_owner(self, saga_id: str) -> Optional[str]:
        resp = self._table.get_item(Key={"saga_id": saga_id})
        item = resp.get("Item")
        if item is None:
            return None
        if int(item["expires_at_epoch_ms"]) <= _now_ms():
            return None
        return item["owner"]
