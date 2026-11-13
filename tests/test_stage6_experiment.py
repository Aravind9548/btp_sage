from concurrent.futures import ThreadPoolExecutor

from saga_bench.event_log import EventLog
from saga_bench.experiment.runner import (
    run_cluster_size_sweep,
    run_concurrency_sweep,
    run_lifo_ablation_sweep,
    run_width_sweep,
)
from saga_bench.experiment.scenario import build_scenario


def test_build_scenario_widens_graph_while_keeping_fixed_edge():
    services, step_order, graph = build_scenario(extra_count=3)
    assert len([s for s in step_order if s.startswith("Extra")]) == 3
    assert ("Payment", "Notification") in graph.edges
    assert step_order[-1] == "Inventory"
    assert set(services.keys()) == set(step_order)


def test_width_sweep_smoke_and_correctness_by_path():
    event_log = EventLog()
    with ThreadPoolExecutor(max_workers=16) as executor:
        rows = run_width_sweep(executor, event_log, widths=[1, 2], instances_per=3, paths=("path_a", "path_b", "path_d"))

    assert len(rows) == 2 * 3 * 3  # 2 widths * 3 instances * 3 paths

    by_path = {}
    for row in rows:
        by_path.setdefault(row["path"], []).append(row)

    assert all(r["correct"] for r in by_path["path_a"])
    assert all(not r["correct"] for r in by_path["path_b"])
    assert all(r["correct"] for r in by_path["path_d"])

    # Path A's makespan should grow with width; Path D's should not.
    a_w1 = [r["makespan_ms"] for r in by_path["path_a"] if r["width"] == 1]
    a_w2 = [r["makespan_ms"] for r in by_path["path_a"] if r["width"] == 2]
    assert sum(a_w2) / len(a_w2) > sum(a_w1) / len(a_w1)


def test_lifo_ablation_sweep_both_correct_lifo_slower():
    event_log = EventLog()
    with ThreadPoolExecutor(max_workers=16) as executor:
        rows = run_lifo_ablation_sweep(executor, event_log, widths=[2], instances_per=3)

    by_path = {}
    for row in rows:
        by_path.setdefault(row["path"], []).append(row)

    assert all(r["correct"] for r in by_path["path_d"])
    assert all(r["correct"] for r in by_path["path_d_lifo"])

    mean_d = sum(r["makespan_ms"] for r in by_path["path_d"]) / len(by_path["path_d"])
    mean_lifo = sum(r["makespan_ms"] for r in by_path["path_d_lifo"]) / len(by_path["path_d_lifo"])
    assert mean_lifo > mean_d


def test_concurrency_sweep_smoke():
    event_log = EventLog()
    with ThreadPoolExecutor(max_workers=32) as executor:
        rows = run_concurrency_sweep(executor, event_log, concurrency_levels=[1, 4], trials_per_level=2)

    assert len(rows) == (1 + 4) * 2
    assert all(r["correct"] for r in rows)


def test_cluster_size_sweep_smoke():
    event_log = EventLog()
    with ThreadPoolExecutor(max_workers=16) as executor:
        rows = run_cluster_size_sweep(executor, event_log, cluster_sizes=[4, 8], instances_per=2)

    assert len(rows) == 2 * 2 * 3  # 2 sizes * 2 instances * 3 paths
    d_rows = [r for r in rows if r["path"] == "path_d"]
    assert all(0.0 <= r["coordination_overhead_ratio"] <= 1.0 for r in d_rows)
