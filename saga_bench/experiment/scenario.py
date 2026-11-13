"""Builds a (services, step_order, graph) scenario for a given number of
extra independent compensations. Used by both the DAG-width sweep (extra
count = width, 1..8) and the cluster-size sweep (extra count = cluster
size - 4, since the base scenario already has 4 services).

FAILING_STEP is always placed last in step_order, so every other step --
base and synthetic alike -- has already completed by the time the failure
is discovered, and the full graph (including the fixed Payment ->
Notification edge) is always exercised regardless of how many extra steps
are added.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from saga_bench.config import (
    COMPENSATION_EDGES,
    EXTRA_STEP_COMPENSATE_MS,
    EXTRA_STEP_EXECUTE_MS,
    FAILING_STEP,
    STEP_ORDER,
    ServiceSpec,
    extra_step_name,
)
from saga_bench.graph import CompensationGraph
from saga_bench.services import Service, build_services


def build_scenario(extra_count: int) -> Tuple[Dict[str, Service], List[str], CompensationGraph]:
    services = build_services()
    non_failing = [s for s in STEP_ORDER if s != FAILING_STEP]

    for i in range(1, extra_count + 1):
        name = extra_step_name(i)
        spec = ServiceSpec(
            name=name,
            execute_ms=EXTRA_STEP_EXECUTE_MS,
            compensate_ms=EXTRA_STEP_COMPENSATE_MS,
            compensating_action=f"release_extra_{i}",
        )
        services[name] = Service(spec)

    step_order = non_failing + [extra_step_name(i) for i in range(1, extra_count + 1)] + [FAILING_STEP]
    graph = CompensationGraph(nodes=set(step_order), edges=list(COMPENSATION_EDGES))
    return services, step_order, graph
