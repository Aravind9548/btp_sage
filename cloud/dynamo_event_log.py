"""DynamoDB-backed EventLog -- drop-in replacement for saga_bench.event_log.EventLog.

Table: EventLog
  PK: saga_id (S)
  SK: timestamp_ms (N) -- stored as Decimal with microsecond precision

Reuses the EventRow dataclass from saga_bench.event_log so downstream code
(verify_rollback, narrate_log) works unchanged.
"""
from __future__ import annotations

import csv
import threading
import time
from decimal import Decimal
from typing import List, Optional

from boto3.dynamodb.conditions import Key

from cloud.config import EVENT_LOG_TABLE, get_resource
from saga_bench.event_log import EventRow


class DynamoEventLog:
    def __init__(
        self,
        table_name: str = EVENT_LOG_TABLE,
        endpoint_url: str | None = None,
    ) -> None:
        resource = get_resource("dynamodb") if endpoint_url is None else get_resource("dynamodb", endpoint_url)
        self._table = resource.Table(table_name)
        self._start = time.perf_counter()
        self._counter = 0
        self._lock = threading.Lock()

    def append(
        self,
        saga_id: str,
        path: str,
        event: str,
        step: Optional[str] = None,
        timestamp_ms: Optional[float] = None,
    ) -> EventRow:
        with self._lock:
            if timestamp_ms is None:
                timestamp_ms = (time.perf_counter() - self._start) * 1000.0
            self._counter += 1
            ts_decimal = Decimal(str(round(timestamp_ms, 6))) + Decimal(str(self._counter)) / Decimal("1000000000")
            thread_id = threading.get_ident()

        item = {
            "saga_id": saga_id,
            "timestamp_ms": ts_decimal,
            "path": path,
            "event": event,
            "thread_id": thread_id,
        }
        if step is not None:
            item["step"] = step

        self._table.put_item(Item=item)

        return EventRow(
            saga_id=saga_id,
            path=path,
            event=event,
            step=step,
            timestamp_ms=float(ts_decimal),
            thread_id=thread_id,
        )

    def rows(self) -> List[EventRow]:
        resp = self._table.scan()
        items = resp.get("Items", [])
        while resp.get("LastEvaluatedKey"):
            resp = self._table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        return sorted(
            [self._item_to_row(item) for item in items],
            key=lambda r: r.timestamp_ms,
        )

    def rows_for(self, saga_id: str) -> List[EventRow]:
        resp = self._table.query(
            KeyConditionExpression=Key("saga_id").eq(saga_id),
            ScanIndexForward=True,
        )
        items = resp.get("Items", [])
        return [self._item_to_row(item) for item in items]

    def to_csv(self, path: str) -> None:
        all_rows = self.rows()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["saga_id", "path", "event", "step", "timestamp_ms", "thread_id"]
            )
            writer.writeheader()
            for row in all_rows:
                writer.writerow({
                    "saga_id": row.saga_id,
                    "path": row.path,
                    "event": row.event,
                    "step": row.step,
                    "timestamp_ms": row.timestamp_ms,
                    "thread_id": row.thread_id,
                })

    @staticmethod
    def _item_to_row(item: dict) -> EventRow:
        return EventRow(
            saga_id=item["saga_id"],
            path=item["path"],
            event=item["event"],
            step=item.get("step"),
            timestamp_ms=float(item["timestamp_ms"]),
            thread_id=int(item.get("thread_id", 0)),
        )
