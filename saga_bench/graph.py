"""Compensation dependency graph as data, plus scheduling helpers.

An edge (a, b) means: compensation `a` must finish before compensation `b`
may start. This is deliberately a plain data structure (nodes + edge list)
rather than hardcoded control flow, so DAG width can be swept in the
experiment stage by adding independent nodes without touching any path's
code.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from saga_bench.config import COMPENSATION_EDGES, STEP_ORDER


@dataclass
class CompensationGraph:
    nodes: Set[str] = field(default_factory=set)
    edges: List[Tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for a, b in self.edges:
            self.nodes.add(a)
            self.nodes.add(b)

    def predecessors(self, node: str) -> Set[str]:
        return {a for a, b in self.edges if b == node}

    def successors(self, node: str) -> Set[str]:
        return {b for a, b in self.edges if a == node}

    def subgraph(self, keep_nodes: Iterable[str]) -> "CompensationGraph":
        """The graph induced by keep_nodes only -- what Path D's elected
        orchestrator builds from the set of steps that actually completed."""
        keep = set(keep_nodes)
        sub_edges = [(a, b) for a, b in self.edges if a in keep and b in keep]
        return CompensationGraph(nodes=set(keep), edges=sub_edges)

    def topological_order(self) -> List[str]:
        in_degree: Dict[str, int] = {n: 0 for n in self.nodes}
        adj: Dict[str, List[str]] = defaultdict(list)
        for a, b in self.edges:
            adj[a].append(b)
            in_degree[b] += 1

        queue = deque(sorted(n for n, d in in_degree.items() if d == 0))
        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in sorted(adj[node]):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(order) != len(self.nodes):
            raise ValueError("compensation graph has a cycle")
        return order

    def ready_steps(self, remaining: Set[str], finished: Set[str]) -> Set[str]:
        """Steps in `remaining` whose predecessors (restricted to this
        graph's nodes) have all already finished -- i.e. safe to dispatch
        right now."""
        ready = set()
        for node in remaining:
            preds = self.predecessors(node) & self.nodes
            if preds <= finished:
                ready.add(node)
        return ready

    def critical_path_length(self, durations: Dict[str, float]) -> float:
        """Longest path through the graph by summed duration, i.e. the
        theoretical minimum makespan for a scheduler with unlimited
        parallelism that still respects every edge."""
        order = self.topological_order()
        best_finish: Dict[str, float] = {}
        for node in order:
            preds = self.predecessors(node) & self.nodes
            start = max((best_finish[p] for p in preds), default=0.0)
            best_finish[node] = start + durations.get(node, 0.0)
        return max(best_finish.values(), default=0.0)


def default_graph() -> CompensationGraph:
    """The graph described in the spec: Payment's refund must finish before
    Notification's cancellation notice starts; Order and Inventory are
    independent of everything."""
    return CompensationGraph(nodes=set(STEP_ORDER), edges=list(COMPENSATION_EDGES))


def verify_rollback(event_log, saga_id: str, graph: Optional[CompensationGraph] = None) -> bool:
    """Check the actual recorded timeline for saga_id against every edge in
    `graph`. Reads only what happened (compensate_started/compensate_finished
    rows in the log), never a scheduler's intentions -- this is the only
    honest way to score correctness for choreographed paths that have no
    central plan to inspect.
    """
    if graph is None:
        graph = default_graph()

    rows = [r for r in event_log.rows_for(saga_id)]

    started: Dict[str, float] = {}
    finished: Dict[str, float] = {}
    for row in rows:
        if row.event == "compensate_started" and row.step is not None:
            started.setdefault(row.step, row.timestamp_ms)
        elif row.event == "compensate_finished" and row.step is not None:
            finished.setdefault(row.step, row.timestamp_ms)

    for a, b in graph.edges:
        if b not in started:
            # b's compensation never ran in this saga -- edge not exercised.
            continue
        if a not in started:
            # a was never compensated either (it never completed forward,
            # so there was nothing to undo) -- b has nothing to wait for.
            continue
        if a not in finished or finished[a] > started[b]:
            # a was compensated but hadn't finished by the time b started.
            return False

    return True
