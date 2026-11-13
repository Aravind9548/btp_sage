"""Deterministic, config-driven fault injection.

No randomness at run time: which step fails, for which saga IDs, is fixed
up front so reruns of an experiment produce identical numbers.

Failure model: `should_fail(saga_id, step)` is checked by a path's forward
loop immediately before it would execute `step`. If it returns True, that
step never executes and every step after it in the forward order is never
attempted either -- only whatever ran *before* the failing step needs
compensating. This mirrors a step whose own action genuinely fails (e.g.
inventory reservation rejected because stock ran out).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class FaultInjector:
    # Explicit per-saga override: saga_id -> step name that should fail.
    per_saga_fail_step: Dict[str, str] = field(default_factory=dict)
    # Fallback applied to every saga_id not present in per_saga_fail_step.
    # None means "no fault by default".
    default_fail_step: Optional[str] = None

    def fail_step_for(self, saga_id: str) -> Optional[str]:
        return self.per_saga_fail_step.get(saga_id, self.default_fail_step)

    def should_fail(self, saga_id: str, step: str) -> bool:
        return self.fail_step_for(saga_id) == step
