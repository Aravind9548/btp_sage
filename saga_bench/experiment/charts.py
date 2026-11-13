"""Turns the tidy results CSV into the four charts plus the stdout summary
table. Matplotlib only, no seaborn -- one chart per file, default styling.
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PATH_LABELS = {
    "path_a": "A: Orchestration",
    "path_b": "B: Choreography",
    "path_d": "D: Election + graph-aware",
    "path_d_lifo": "D (LIFO ablation)",
}
PATH_COLORS = {
    "path_a": "#4C72B0",
    "path_b": "#DD8452",
    "path_d": "#55A868",
    "path_d_lifo": "#8172B2",
}


def chart_makespan_vs_width(df: pd.DataFrame, out_path: str) -> None:
    sub = df[df["sweep"] == "dag_width"]
    agg = sub.groupby(["path", "width"])["makespan_ms"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(7, 5))
    for path in ("path_a", "path_b", "path_d"):
        data = agg[agg["path"] == path].sort_values("width")
        ax.plot(data["width"], data["makespan_ms"], marker="o", label=PATH_LABELS[path], color=PATH_COLORS[path])

    ax.set_xlabel("DAG width (independent extra compensations)")
    ax.set_ylabel("Mean compensation makespan (ms)")
    ax.set_title("Makespan vs. DAG width")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_correctness_rate(df: pd.DataFrame, out_path_bar: str, out_path_table: str) -> pd.DataFrame:
    sub = df[df["sweep"].isin(["dag_width", "lifo_ablation"])]
    rate = sub.groupby("path")["correct"].mean().reset_index()
    rate["correctness_rate"] = rate["correct"]
    rate = rate[["path", "correctness_rate"]].sort_values("path")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    labels = [PATH_LABELS.get(p, p) for p in rate["path"]]
    colors = [PATH_COLORS.get(p, "#888888") for p in rate["path"]]
    ax.bar(labels, rate["correctness_rate"], color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Correctness rate")
    ax.set_title("Rollback correctness rate by path")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    for i, v in enumerate(rate["correctness_rate"]):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center")
    fig.tight_layout()
    fig.savefig(out_path_bar, dpi=150)
    plt.close(fig)

    rate.to_csv(out_path_table, index=False)
    return rate


def chart_lifo_ablation(df: pd.DataFrame, out_path: str) -> None:
    sub = df[df["sweep"] == "lifo_ablation"]
    agg = sub.groupby(["path", "width"])["makespan_ms"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(7, 5))
    for path in ("path_d", "path_d_lifo"):
        data = agg[agg["path"] == path].sort_values("width")
        ax.plot(data["width"], data["makespan_ms"], marker="o", label=PATH_LABELS[path], color=PATH_COLORS[path])

    ax.set_xlabel("DAG width (independent extra compensations)")
    ax.set_ylabel("Mean compensation makespan (ms)")
    ax.set_title("Ablation: dependency-aware scheduler vs. naive LIFO\n(both behind the same election)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def chart_overhead_vs_cluster_size(df: pd.DataFrame, out_path: str) -> None:
    sub = df[df["sweep"] == "cluster_size"]
    agg = sub.groupby(["path", "cluster_size"])["coordination_overhead_ratio"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(7, 5))
    for path in ("path_a", "path_b", "path_d"):
        data = agg[agg["path"] == path].sort_values("cluster_size")
        ax.plot(data["cluster_size"], data["coordination_overhead_ratio"], marker="o", label=PATH_LABELS[path], color=PATH_COLORS[path])

    ax.set_xlabel("Cluster size (number of services)")
    ax.set_ylabel("Coordination overhead ratio")
    ax.set_title("Coordination overhead vs. cluster size")
    ax.set_ylim(bottom=0)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def print_summary_table(df: pd.DataFrame) -> None:
    sub = df[df["sweep"].isin(["dag_width", "lifo_ablation"])]
    summary = sub.groupby("path").agg(
        mean_makespan_ms=("makespan_ms", "mean"),
        correctness_rate=("correct", "mean"),
        mean_overhead_ratio=("coordination_overhead_ratio", "mean"),
        n=("saga_id", "count"),
    ).reset_index()
    summary["path"] = summary["path"].map(lambda p: PATH_LABELS.get(p, p))
    summary = summary.round({"mean_makespan_ms": 1, "correctness_rate": 3, "mean_overhead_ratio": 4})

    print("\n=== Summary: path, mean makespan, correctness rate, overhead ratio ===")
    print(summary.to_string(index=False))
    print()


def generate_all_charts(df: pd.DataFrame, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    chart_makespan_vs_width(df, os.path.join(out_dir, "chart1_makespan_vs_width.png"))
    chart_correctness_rate(
        df,
        os.path.join(out_dir, "chart2_correctness_rate.png"),
        os.path.join(out_dir, "chart2_correctness_rate_table.csv"),
    )
    chart_lifo_ablation(df, os.path.join(out_dir, "chart3_lifo_ablation.png"))
    chart_overhead_vs_cluster_size(df, os.path.join(out_dir, "chart4_overhead_vs_cluster_size.png"))
    print_summary_table(df)
