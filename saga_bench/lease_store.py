"""In-process lease store used for leader election over a saga_id.

Models a DynamoDB conditional write with `attribute_not_exists(saga_id)`:
`try_acquire` is the local equivalent of a `PutItem` guarded by that
condition expression, and TTL expiry is the local equivalent of a DynamoDB
TTL attribute reaping the item so it becomes acquirable again. Here the
"table" is a dict and the "condition expression" is enforced by holding a
mutex for the duration of the check-then-set.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class _Lease:
    owner: str
    expires_at_ms: float


class LeaseStore:
    def __init__(self) -> None:
        self._leases: Dict[str, _Lease] = {}
        self._lock = threading.Lock()

    def try_acquire(self, saga_id: str, owner: str, ttl_ms: float = 2000.0) -> bool:
        now = time.monotonic() * 1000.0
        with self._lock:
            existing = self._leases.get(saga_id)
            if existing is not None and existing.expires_at_ms > now:
                return False
            self._leases[saga_id] = _Lease(owner=owner, expires_at_ms=now + ttl_ms)
            return True

    def renew(self, saga_id: str, owner: str, ttl_ms: float = 2000.0) -> bool:
        now = time.monotonic() * 1000.0
        with self._lock:
            existing = self._leases.get(saga_id)
            if existing is None or existing.owner != owner or existing.expires_at_ms <= now:
                return False
            existing.expires_at_ms = now + ttl_ms
            return True

    def release(self, saga_id: str, owner: str) -> bool:
        with self._lock:
            existing = self._leases.get(saga_id)
            if existing is None or existing.owner != owner:
                return False
            del self._leases[saga_id]
            return True

    def current_owner(self, saga_id: str) -> Optional[str]:
        now = time.monotonic() * 1000.0
        with self._lock:
            existing = self._leases.get(saga_id)
            if existing is None or existing.expires_at_ms <= now:
                return None
            return existing.owner
