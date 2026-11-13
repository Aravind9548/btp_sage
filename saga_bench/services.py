"""The four saga step services. No real business logic -- execute() and
compensate() just sleep for the configured duration and emit log rows.
"""
from __future__ import annotations

import time
from typing import Optional

from saga_bench.config import SERVICES, ServiceSpec
from saga_bench.event_log import EventLog
from saga_bench.saga_store import SagaStore


class Service:
    def __init__(self, spec: ServiceSpec) -> None:
        self.spec = spec

    def execute(self, saga_id: str, path: str, event_log: EventLog) -> None:
        event_log.append(saga_id, path, "execute_started", self.spec.name)
        time.sleep(self.spec.execute_ms / 1000.0)
        event_log.append(saga_id, path, "execute_finished", self.spec.name)

    def compensate(
        self,
        saga_id: str,
        path: str,
        event_log: EventLog,
        saga_store: Optional[SagaStore] = None,
    ) -> bool:
        """Run the compensating action. If `saga_store` is given, the step
        name doubles as the idempotency key: a compensation that already
        ran (per SagaStore.mark_compensated) is skipped rather than re-run,
        which is what makes re-elected Path D orchestrators safe.

        Returns True if the compensation actually ran, False if it was
        skipped as a duplicate.
        """
        if saga_store is not None:
            first_time = saga_store.mark_compensated(saga_id, self.spec.name)
            if not first_time:
                event_log.append(saga_id, path, "compensate_skipped_duplicate", self.spec.name)
                return False

        event_log.append(saga_id, path, "compensate_started", self.spec.name)
        time.sleep(self.spec.compensate_ms / 1000.0)
        event_log.append(saga_id, path, "compensate_finished", self.spec.name)
        return True


def build_services() -> dict:
    return {name: Service(spec) for name, spec in SERVICES.items()}
