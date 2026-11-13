"""Single source of truth for service timings and the compensation graph.

These durations are a stated modelling assumption, not measurements from a
real system. Changing the experiment's timing profile means editing this
file only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    execute_ms: float
    compensate_ms: float
    compensating_action: str


SERVICES: Dict[str, ServiceSpec] = {
    "Order": ServiceSpec("Order", execute_ms=100, compensate_ms=150, compensating_action="cancel_order"),
    "Payment": ServiceSpec("Payment", execute_ms=300, compensate_ms=800, compensating_action="refund"),
    "Inventory": ServiceSpec("Inventory", execute_ms=200, compensate_ms=200, compensating_action="release_reservation"),
    "Notification": ServiceSpec("Notification", execute_ms=50, compensate_ms=100, compensating_action="send_cancellation_notice"),
}

# The order steps normally execute in (also the order Path A compensates in,
# reversed). Notification is deliberately placed BEFORE Payment in the
# forward chain -- e.g. "we received your order" is sent immediately after
# Order, well before the customer is actually charged. That choice is what
# lets Path A's naive "reverse of forward order" coordinator satisfy the
# Payment-before-Notification compensation constraint (compensating in
# reverse puts Payment ahead of Notification) without the coordinator
# knowing anything about the dependency graph. It is a property of this
# particular hand-picked schedule, not a general guarantee -- reorder these
# two and Path A breaks too. Path D is the one that respects the
# constraint by construction, for any completed subset and any order.
STEP_ORDER: List[str] = ["Order", "Notification", "Payment", "Inventory"]

# Compensation dependency graph as data: an edge (a, b) means compensation
# `a` must finish before compensation `b` may start. This is the thing
# choreography (Path B) is blind to and Path D respects.
COMPENSATION_EDGES: List[Tuple[str, str]] = [
    ("Payment", "Notification"),
]

# The step whose failure triggers a rollback in the main experiment: it is
# always last in any step order used by the experiment runner, so every
# real (and, for the DAG-width sweep, every synthetic) step upstream of it
# has already completed and needs compensating. This is what exercises the
# Payment-before-Notification constraint on every single injected failure.
FAILING_STEP = "Inventory"

# DAG-width sweep: synthetic, mutually-independent extra steps added to
# widen the graph while the Payment->Notification edge stays fixed. Their
# durations are a stated modelling assumption (not derived from the four
# real services): execute is kept small so the sweep's forward phase stays
# cheap, while compensate is deliberately smaller than Payment's 800ms so
# that adding more of them never changes Path B/D's critical path -- only
# Path A's fully-serial sum grows with width, which is the effect the
# sweep exists to show.
EXTRA_STEP_EXECUTE_MS = 10.0
EXTRA_STEP_COMPENSATE_MS = 200.0


def extra_step_name(index: int) -> str:
    return f"Extra{index}"
