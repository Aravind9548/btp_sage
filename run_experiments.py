"""Runs the full saga-coordination experiment sweep and writes:

  results/experiment_results.csv   -- one tidy row per saga run
  results/events.csv               -- every raw event from every saga run
  results/chart1_makespan_vs_width.png
  results/chart2_correctness_rate.png (+ _table.csv)
  results/chart3_lifo_ablation.png
  results/chart4_overhead_vs_cluster_size.png

Must complete in under five minutes (see saga_bench/experiment/runner.py
for the timing budget reasoning) and must produce the same aggregate
numbers on every run: no RNG anywhere, fault injection is fully
config-driven. Individual wall-clock timestamps carry a little OS
thread-scheduling jitter because service work is real time.sleep(), as the
spec requires -- see runner.py's module docstring.
"""
from __future__ import annotations

import os

import pandas as pd

from saga_bench.experiment.charts import generate_all_charts
from saga_bench.experiment.runner import run_all

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Running experiment sweeps (DAG width, LIFO ablation, concurrency, cluster size)...")
    rows, event_log, elapsed_s = run_all(max_workers=48)
    print(f"All sweeps finished in {elapsed_s:.1f}s ({len(rows)} saga runs recorded).")

    df = pd.DataFrame(rows)
    csv_path = os.path.join(RESULTS_DIR, "experiment_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"Wrote tidy results CSV: {csv_path}")

    events_csv_path = os.path.join(RESULTS_DIR, "events.csv")
    event_log.to_csv(events_csv_path)
    print(f"Wrote raw event log CSV: {events_csv_path}")

    generate_all_charts(df, RESULTS_DIR)
    print(f"Wrote charts to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
