"""Thread-safe per-saga state: which steps completed, which were compensated.

Models a saga's row in a state table (e.g. a DynamoDB item keyed by
saga_id). One lock per saga_id keeps unrelated sagas from contending with
each other under concurrent load.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, Set


class SagaStore:
    def __init__(self) -> None:
        self._completed: Dict[str, Set[str]] = defaultdict(set)
        self._compensated: Dict[str, Set[str]] = defaultdict(set)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def _lock_for(self, saga_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks[saga_id]

    def mark_completed(self, saga_id: str, step: str) -> None:
        with self._lock_for(saga_id):
            self._completed[saga_id].add(step)

    def mark_compensated(self, saga_id: str, step: str) -> bool:
        """Record that a compensation ran. Returns False if it already had,
        so callers can detect duplicate/idempotent compensation attempts."""
        with self._lock_for(saga_id):
            if step in self._compensated[saga_id]:
                return False
            self._compensated[saga_id].add(step)
            return True

    def is_compensated(self, saga_id: str, step: str) -> bool:
        with self._lock_for(saga_id):
            return step in self._compensated[saga_id]

    def completed_steps(self, saga_id: str) -> Set[str]:
        with self._lock_for(saga_id):
            return set(self._completed[saga_id])

    def compensated_steps(self, saga_id: str) -> Set[str]:
        with self._lock_for(saga_id):
            return set(self._compensated[saga_id])
