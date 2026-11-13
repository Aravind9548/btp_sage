"""DynamoDB-backed SagaStore -- drop-in replacement for saga_bench.saga_store.SagaStore.

Table: SagaState
  PK: saga_id (S)
  Attributes: completed_steps (SS), compensated_steps (SS)

mark_compensated uses a ConditionExpression to return False when the step
was already compensated (idempotency), mirroring the in-memory version's
set-membership check.
"""
from __future__ import annotations

from typing import Set

from botocore.exceptions import ClientError

from cloud.config import SAGA_STATE_TABLE, get_resource


class DynamoSagaStore:
    def __init__(
        self,
        table_name: str = SAGA_STATE_TABLE,
        endpoint_url: str | None = None,
    ) -> None:
        resource = get_resource("dynamodb") if endpoint_url is None else get_resource("dynamodb", endpoint_url)
        self._table = resource.Table(table_name)

    def mark_completed(self, saga_id: str, step: str) -> None:
        self._table.update_item(
            Key={"saga_id": saga_id},
            UpdateExpression="ADD completed_steps :s",
            ExpressionAttributeValues={":s": {step}},
        )

    def mark_compensated(self, saga_id: str, step: str) -> bool:
        try:
            self._table.update_item(
                Key={"saga_id": saga_id},
                UpdateExpression="ADD compensated_steps :s",
                ConditionExpression="attribute_not_exists(compensated_steps) OR NOT contains(compensated_steps, :step)",
                ExpressionAttributeValues={":s": {step}, ":step": step},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def is_compensated(self, saga_id: str, step: str) -> bool:
        return step in self.compensated_steps(saga_id)

    def completed_steps(self, saga_id: str) -> Set[str]:
        resp = self._table.get_item(Key={"saga_id": saga_id})
        item = resp.get("Item", {})
        return set(item.get("completed_steps", set()))

    def compensated_steps(self, saga_id: str) -> Set[str]:
        resp = self._table.get_item(Key={"saga_id": saga_id})
        item = resp.get("Item", {})
        return set(item.get("compensated_steps", set()))
