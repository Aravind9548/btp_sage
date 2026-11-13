"""Append-only structured event log shared across services/paths.

One EventLog is used per experiment run. Every row is timestamped relative
to the log's creation, in milliseconds, using a monotonic clock so ordering
is meaningful even when the wall clock jumps. `verify_rollback` (stage 2)
reads this log to score correctness -- it never trusts a scheduler's
intentions, only what actually happened and when.
"""
from __future__ import annotations

import csv
import threading
import time
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass(frozen=True)
class EventRow:
    saga_id: str
    path: str
    event: str
    step: Optional[str]
    timestamp_ms: float
    thread_id: int


class EventLog:
    def __init__(self) -> None:
        # perf_counter, not monotonic: on this platform monotonic() is
        # backed by GetTickCount64 with ~15ms resolution, which is too
        # coarse to order events reliably; perf_counter uses
        # QueryPerformanceCounter and resolves sub-microsecond gaps.
        self._start = time.perf_counter()
        self._rows: List[EventRow] = []
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
            # Timestamp is taken while holding the lock so that the row's
            # position in self._rows always matches its timestamp order,
            # even when multiple threads race to append. `timestamp_ms` can
            # be supplied explicitly for hand-constructed logs (tests).
            if timestamp_ms is None:
                timestamp_ms = (time.perf_counter() - self._start) * 1000.0
            row = EventRow(
                saga_id=saga_id,
                path=path,
                event=event,
                step=step,
                timestamp_ms=timestamp_ms,
                thread_id=threading.get_ident(),
            )
            self._rows.append(row)
            return row

    def rows(self) -> List[EventRow]:
        with self._lock:
            return list(self._rows)

    def rows_for(self, saga_id: str) -> List[EventRow]:
        with self._lock:
            return [r for r in self._rows if r.saga_id == saga_id]

    def to_csv(self, path: str) -> None:
        rows = self.rows()
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["saga_id", "path", "event", "step", "timestamp_ms", "thread_id"]
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
