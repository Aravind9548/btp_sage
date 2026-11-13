"""Produces presentation-grade figures and tables from the existing tidy
results CSV (results/experiment_results.csv). Does NOT re-run the
experiment and does NOT touch saga_bench/ -- every number on every figure
or table is computed here, from that CSV, and logged to
slides/key_numbers.md so nothing is untraceable.

Run: .venv\\Scripts\\python.exe make_slides.py
Reads:  results/experiment_results.csv
Writes: slides/fig1_makespan_vs_width.png
        slides/fig2_correctness.png
        slides/fig3_ablation.png
        slides/fig4_premium.png
        slides/fig5_makespan_vs_cluster_size.png
        slides/fig6_concurrency_degradation.png
        slides/table1_summary.png + .md
        slides/table2_knownanswer.png + .md
        slides/key_numbers.md
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "results", "experiment_results.csv")
OUT_DIR = os.path.join(os.path.dirname(__file__), "slides")

# ---------------------------------------------------------------------------
# Styling: colorblind-safe (Okabe-Ito) palette, one color+marker+linestyle
# per path, held constant across every figure.
# ---------------------------------------------------------------------------
PATH_LABEL = {
    "path_a": "A: Orchestration",
    "path_b": "B: Choreography",
    "path_d": "D: Election + graph-aware",
    "path_d_lifo": "D (naive LIFO ablation)",
}
# Shorter aliases for table cells, which have much less horizontal room
# per path than a figure legend does.
PATH_LABEL_SHORT = {
    "path_a": "A: Orchestration",
    "path_b": "B: Choreography",
    "path_d": "D: Graph-aware",
    "path_d_lifo": "D: LIFO ablation",
}
PATH_STYLE = {
    "path_a": dict(color="#0072B2", marker="o", linestyle="-"),
    "path_b": dict(color="#E69F00", marker="s", linestyle="--"),
    "path_d": dict(color="#009E73", marker="^", linestyle="-."),
    "path_d_lifo": dict(color="#CC79A7", marker="D", linestyle=":"),
}

FIG_W_IN, FIG_H_IN, DPI = 8.0, 4.5, 200  # 1600x900 px at 200 dpi
BASE_FONT, LABEL_FONT, TITLE_FONT = 18, 20, 24
LINEWIDTH, MARKERSIZE = 3, 10

plt.rcParams.update(
    {
        "font.size": BASE_FONT,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.grid": False,
    }
)


def style_axes(ax, xlabel: str, ylabel: str, title: str, title_fontsize: int = TITLE_FONT) -> None:
    ax.set_xlabel(xlabel, fontsize=LABEL_FONT)
    ax.set_ylabel(ylabel, fontsize=LABEL_FONT)
    ax.set_title(title, fontsize=title_fontsize)
    ax.grid(axis="y", color="#cccccc", linewidth=0.8, zorder=0)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


# ---------------------------------------------------------------------------
# Number registry: every value that lands on a figure or table is recorded
# here with the CSV column(s) and computation that produced it, then dumped
# to key_numbers.md at the end.
# ---------------------------------------------------------------------------
class NumberRegistry:
    def __init__(self) -> None:
        self.entries = []

    def record(self, label: str, value, csv_columns: str, computation: str):
        self.entries.append({"label": label, "value": value, "csv_columns": csv_columns, "computation": computation})
        return value

    def to_markdown(self) -> str:
        lines = [
            "# Key numbers",
            "",
            "Every number appearing on any figure or table in `slides/`, with the",
            "CSV column(s) and computation that produced it. Source data:",
            f"`{os.path.relpath(RESULTS_CSV, os.path.dirname(__file__))}`. Nothing here is hardcoded --",
            "regenerate by rerunning `make_slides.py` against a fresh sweep.",
            "",
            "| # | Label | Value | CSV column(s) | Computation |",
            "|---|---|---|---|---|",
        ]
        for i, e in enumerate(self.entries, 1):
            v = e["value"]
            v_str = f"{v:.2f}" if isinstance(v, float) else str(v)
            lines.append(f"| {i} | {e['label']} | {v_str} | {e['csv_columns']} | {e['computation']} |")
        return "\n".join(lines) + "\n"


REG = NumberRegistry()


def load_data() -> pd.DataFrame:
    df = pd.read_csv(RESULTS_CSV)
    df["correct"] = df["correct"].astype(str).str.strip().eq("True")
    return df


# ---------------------------------------------------------------------------
# fig1: makespan vs DAG width, one line per path, shaded mean +/- std band,
# width=1 values annotated. Headline figure.
# ---------------------------------------------------------------------------
def fig1_makespan_vs_width(df: pd.DataFrame) -> None:
    sub = df[df["sweep"] == "dag_width"]
    paths = ["path_a", "path_b", "path_d"]

    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
    w1_values = {}
    for path in paths:
        agg = sub[sub["path"] == path].groupby("width")["makespan_ms"].agg(["mean", "std", "count"]).reset_index()
        agg = agg.sort_values("width")
        style = PATH_STYLE[path]
        ax.plot(
            agg["width"], agg["mean"], label=PATH_LABEL_SHORT[path], linewidth=LINEWIDTH, markersize=MARKERSIZE, **style,
            zorder=3,
        )
        lower = (agg["mean"] - agg["std"]).clip(lower=0)
        upper = agg["mean"] + agg["std"]
        ax.fill_between(agg["width"], lower, upper, color=style["color"], alpha=0.15, linewidth=0, zorder=2)

        w1 = agg[agg["width"] == 1].iloc[0]
        w1_values[path] = float(w1["mean"])
        REG.record(
            f"fig1: {PATH_LABEL[path]} mean makespan at width=1",
            float(w1["mean"]),
            "makespan_ms (filtered sweep=dag_width, path, width=1)",
            "groupby(path, width)['makespan_ms'].mean()",
        )

    # A single grouped callout, kept narrow and short (single-letter path
    # tags, not full names) and pinned to the empty upper-left corner: at
    # x<=2.8 the A line is still well under 1500, so a block sitting at
    # y>=2150 there stays clear of A's line, and is far above the flat B/D
    # band (~800-1050) regardless of x.
    short_tag = {"path_a": "A", "path_b": "B", "path_d": "D"}
    ax.text(1.15, 2950, "At width = 1:", fontsize=BASE_FONT - 4, fontweight="bold", color="#333333", va="top")
    for i, path in enumerate(paths):
        style = PATH_STYLE[path]
        ax.text(
            1.15, 2950 - (i + 1) * 230, f"{short_tag[path]}: {w1_values[path]:.0f} ms",
            fontsize=BASE_FONT - 3, fontweight="bold", color=style["color"], va="top",
        )

    ax.set_xlim(0.7, 8.9)
    ax.set_ylim(0, 3100)
    style_axes(ax, "DAG width (independent extra compensations)", "Makespan (ms)", "Makespan vs. DAG width")
    fig.subplots_adjust(left=0.16, right=0.72, top=0.88, bottom=0.20)
    # Anchored to the FIGURE (not the axes), upper-right corner pinned just
    # inside the canvas -- guarantees the legend can never run past the
    # 1600x900 canvas edge regardless of label length.
    ax.legend(fontsize=13, loc="upper right", bbox_to_anchor=(0.99, 0.93), bbox_transform=fig.transFigure, frameon=False)
    fig.savefig(os.path.join(OUT_DIR, "fig1_makespan_vs_width.png"), dpi=DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig2: correctness rate per path, horizontal bars, sorted worst to best,
# exact percentage on each bar.
# ---------------------------------------------------------------------------
def fig2_correctness(df: pd.DataFrame) -> None:
    sub = df[df["sweep"].isin(["dag_width", "lifo_ablation"])]
    rate = sub.groupby("path")["correct"].mean().reset_index()
    rate = rate.sort_values("correct")  # worst to best

    for _, row in rate.iterrows():
        REG.record(
            f"fig2/table1: correctness rate, {PATH_LABEL[row['path']]}",
            float(row["correct"]) * 100,
            "correct (filtered sweep in [dag_width, lifo_ablation])",
            "groupby(path)['correct'].mean() * 100",
        )

    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
    labels = [PATH_LABEL_SHORT[p] for p in rate["path"]]
    colors = [PATH_STYLE[p]["color"] for p in rate["path"]]
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, rate["correct"] * 100, color=colors, zorder=3, height=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=BASE_FONT - 2)
    ax.set_xlim(0, 100)
    for bar, val in zip(bars, rate["correct"] * 100):
        if val >= 15:
            # Label inside the bar, right-aligned, so it never gets clipped
            # by the axes edge regardless of value.
            ax.text(val - 2, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%", va="center", ha="right",
                     fontsize=BASE_FONT, color="white", fontweight="bold", zorder=4)
        else:
            ax.text(val + 2, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%", va="center", ha="left",
                     fontsize=BASE_FONT, color="black", fontweight="bold", zorder=4)

    style_axes(ax, "Correctness rate (%)", "", "Correctness rate by path\n(worst to best)")
    ax.grid(axis="x", color="#cccccc", linewidth=0.8, zorder=0)
    ax.grid(axis="y", visible=False)
    fig.subplots_adjust(left=0.34, right=0.95, top=0.80, bottom=0.20)
    fig.savefig(os.path.join(OUT_DIR, "fig2_correctness.png"), dpi=DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig3: Path D ablation -- naive LIFO vs dependency-aware, makespan vs
# width. Annotate the gap at the widest point, in ms and %.
# ---------------------------------------------------------------------------
def fig3_ablation(df: pd.DataFrame) -> None:
    sub = df[df["sweep"] == "lifo_ablation"]
    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))

    aggs = {}
    for path in ("path_d", "path_d_lifo"):
        agg = sub[sub["path"] == path].groupby("width")["makespan_ms"].mean().reset_index().sort_values("width")
        aggs[path] = agg
        style = PATH_STYLE[path]
        ax.plot(agg["width"], agg["makespan_ms"], label=PATH_LABEL_SHORT[path], linewidth=LINEWIDTH, markersize=MARKERSIZE, **style)

    max_width = int(sub["width"].max())
    d_at_max = float(aggs["path_d"][aggs["path_d"]["width"] == max_width]["makespan_ms"].iloc[0])
    lifo_at_max = float(aggs["path_d_lifo"][aggs["path_d_lifo"]["width"] == max_width]["makespan_ms"].iloc[0])
    gap_ms = lifo_at_max - d_at_max
    gap_pct = gap_ms / d_at_max * 100

    REG.record(f"fig3: dependency-aware makespan at width={max_width}", d_at_max, "makespan_ms (sweep=lifo_ablation, path=path_d)", f"groupby(width)['makespan_ms'].mean() at width={max_width}")
    REG.record(f"fig3: LIFO makespan at width={max_width}", lifo_at_max, "makespan_ms (sweep=lifo_ablation, path=path_d_lifo)", f"groupby(width)['makespan_ms'].mean() at width={max_width}")
    REG.record(f"fig3: LIFO-vs-graph-aware gap at width={max_width} (ms)", gap_ms, "makespan_ms", "lifo_mean - dependency_aware_mean at max width")
    REG.record(f"fig3: LIFO-vs-graph-aware gap at width={max_width} (%)", gap_pct, "makespan_ms", "gap_ms / dependency_aware_mean * 100")

    ax.annotate(
        f"gap: {gap_ms:.0f} ms\n({gap_pct:.0f}% slower)",
        xy=(max_width, (d_at_max + lifo_at_max) / 2),
        xytext=(max_width - 2.6, d_at_max - 350),
        fontsize=BASE_FONT - 2,
        fontweight="bold",
        va="top",
        arrowprops=dict(arrowstyle="->", lw=2),
    )

    ax.set_xlim(0.7, 8.9)
    ax.set_ylim(bottom=0)
    style_axes(
        ax,
        "DAG width (independent extra compensations)",
        "Makespan (ms)",
        "Ablation: scheduler vs. naive LIFO\n(same election, different dispatch)",
    )
    fig.subplots_adjust(left=0.16, right=0.72, top=0.80, bottom=0.20)
    ax.legend(fontsize=13, loc="upper right", bbox_to_anchor=(0.99, 0.76), bbox_transform=fig.transFigure, frameon=False)
    fig.savefig(os.path.join(OUT_DIR, "fig3_ablation.png"), dpi=DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig4: two stacked panels sharing the x-axis (DAG width). Top: makespan
# for B and D only, gap shaded and labelled. Bottom: correctness for B and
# D. The bounded-latency-premium figure.
# ---------------------------------------------------------------------------
def fig4_premium(df: pd.DataFrame) -> None:
    sub = df[(df["sweep"] == "dag_width") & (df["path"].isin(["path_b", "path_d"]))]

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(FIG_W_IN, FIG_H_IN), sharex=True, gridspec_kw={"height_ratios": [2.4, 1]}
    )

    makespan_by_width = {}
    for path in ("path_b", "path_d"):
        agg = sub[sub["path"] == path].groupby("width")["makespan_ms"].mean().reset_index().sort_values("width")
        makespan_by_width[path] = agg
        style = PATH_STYLE[path]
        ax_top.plot(
            agg["width"], agg["makespan_ms"], label=PATH_LABEL_SHORT[path], linewidth=LINEWIDTH, markersize=MARKERSIZE,
            zorder=3, **style,
        )

    widths = makespan_by_width["path_b"]["width"].values
    b_vals = makespan_by_width["path_b"]["makespan_ms"].values
    d_vals = makespan_by_width["path_d"]["makespan_ms"].values
    ax_top.fill_between(widths, b_vals, d_vals, color="#999999", alpha=0.3, zorder=1)

    gap_ms_per_width = d_vals - b_vals
    mean_gap_ms = float(np.mean(gap_ms_per_width))
    mean_gap_pct = float(np.mean(gap_ms_per_width / b_vals * 100))
    REG.record("fig4: mean D-over-B makespan premium (ms), averaged over DAG widths 1-8", mean_gap_ms, "makespan_ms (sweep=dag_width, path in [path_b, path_d])", "mean over width of (D_mean_makespan - B_mean_makespan)")
    REG.record("fig4: mean D-over-B makespan premium (%), averaged over DAG widths 1-8", mean_gap_pct, "makespan_ms", "mean over width of ((D_mean - B_mean) / B_mean * 100)")

    # Annotate near the right edge, well above both lines, with a leader
    # pointing down into the shaded gap -- clear of the legend (lower
    # right) and the lines themselves.
    anno_w = 5.5
    anno_y_data = float(np.interp(anno_w, widths, (b_vals + d_vals) / 2))
    ax_top.annotate(
        f"bounded premium: ~{mean_gap_ms:.0f} ms (~{mean_gap_pct:.0f}%)",
        xy=(anno_w, anno_y_data),
        xytext=(2.0, 1550),
        fontsize=BASE_FONT - 3,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", lw=2),
    )

    ax_top.set_ylim(0, 1900)
    ax_top.set_ylabel("Makespan\n(ms)", fontsize=LABEL_FONT - 2)
    ax_top.grid(axis="y", color="#cccccc", linewidth=0.8, zorder=0)
    ax_top.set_axisbelow(True)
    for spine in ("top", "right"):
        ax_top.spines[spine].set_visible(False)
    # Lower-left corner of the top panel is empty (B/D sit at 800-1050,
    # well above 0) regardless of width, so the legend goes there instead
    # of fighting with the annotation for the top-right corner.
    ax_top.legend(fontsize=13, loc="lower left", frameon=True, facecolor="white", framealpha=0.9, edgecolor="none")

    for path in ("path_b", "path_d"):
        agg = sub[sub["path"] == path].groupby("width")["correct"].mean().reset_index().sort_values("width")
        style = PATH_STYLE[path]
        ax_bot.plot(agg["width"], agg["correct"] * 100, linewidth=LINEWIDTH, markersize=MARKERSIZE, zorder=3, **style)
        REG.record(
            f"fig4 (bottom): {PATH_LABEL[path]} correctness rate (flat across widths)",
            float(agg["correct"].mean()) * 100,
            "correct (sweep=dag_width)",
            "groupby(path, width)['correct'].mean() * 100, averaged over width",
        )

    ax_bot.set_xlim(0.7, 8.9)
    ax_bot.set_ylim(-8, 108)
    ax_bot.set_yticks([0, 100])
    ax_bot.set_xlabel("DAG width (independent extra compensations)", fontsize=LABEL_FONT)
    ax_bot.set_ylabel("Correct\n(%)", fontsize=LABEL_FONT - 2)
    ax_bot.grid(axis="y", color="#cccccc", linewidth=0.8, zorder=0)
    ax_bot.set_axisbelow(True)
    for spine in ("top", "right"):
        ax_bot.spines[spine].set_visible(False)

    fig.suptitle("D pays a small, flat premium for correctness", fontsize=20, y=0.995)
    fig.subplots_adjust(left=0.18, right=0.95, top=0.83, bottom=0.16, hspace=0.45)
    fig.savefig(os.path.join(OUT_DIR, "fig4_premium.png"), dpi=DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig5: makespan vs. cluster size (number of services) -- the sweep this
# field's reference comparison (Rudrabhatla 2018, IJACSA) reports directly,
# so titled and framed to sit next to that number. One line per path, same
# styling as fig1, slope of each line annotated (ms per added service).
# ---------------------------------------------------------------------------
def fig5_makespan_vs_cluster_size(df: pd.DataFrame) -> None:
    sub = df[df["sweep"] == "cluster_size"]
    paths = ["path_a", "path_b", "path_d"]

    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
    slopes = {}
    for path in paths:
        agg = sub[sub["path"] == path].groupby("cluster_size")["makespan_ms"].mean().reset_index().sort_values("cluster_size")
        style = PATH_STYLE[path]
        ax.plot(
            agg["cluster_size"], agg["makespan_ms"], label=PATH_LABEL_SHORT[path],
            linewidth=LINEWIDTH, markersize=MARKERSIZE, zorder=3, **style,
        )
        slope, intercept = np.polyfit(agg["cluster_size"], agg["makespan_ms"], 1)
        slopes[path] = float(slope)
        REG.record(
            f"fig5: {PATH_LABEL[path]} slope (ms per added service)",
            float(slope),
            "makespan_ms (filtered sweep=cluster_size)",
            "np.polyfit(cluster_size, groupby(path, cluster_size)['makespan_ms'].mean(), deg=1)[0]",
        )
        last_x, last_y = agg["cluster_size"].iloc[-1], agg["makespan_ms"].iloc[-1]
        slopes[f"{path}_xy"] = (last_x, last_y)

    # A ends far above B/D, so its label sits beside its own last point; B
    # and D end almost on top of each other (~800-950ms) so their labels
    # are stacked vertically off to the side instead of both anchored at
    # y=last_y, which is what caused them to collide.
    a_x, a_y = slopes["path_a_xy"]
    ax.annotate(f"{slopes['path_a']:+.1f} ms/service", xy=(a_x, a_y), xytext=(8, 0), textcoords="offset points",
                fontsize=BASE_FONT - 5, fontweight="bold", color=PATH_STYLE["path_a"]["color"], va="center")
    d_x, d_y = slopes["path_d_xy"]
    ax.annotate(f"{slopes['path_d']:+.1f} ms/service", xy=(d_x, d_y), xytext=(8, 16), textcoords="offset points",
                fontsize=BASE_FONT - 5, fontweight="bold", color=PATH_STYLE["path_d"]["color"], va="center")
    b_x, b_y = slopes["path_b_xy"]
    ax.annotate(f"{slopes['path_b']:+.1f} ms/service", xy=(b_x, b_y), xytext=(8, -22), textcoords="offset points",
                fontsize=BASE_FONT - 5, fontweight="bold", color=PATH_STYLE["path_b"]["color"], va="center")

    ax.set_xlim(3.2, 19.5)
    style_axes(ax, "Number of services (cluster size)", "Mean makespan (ms)", "Makespan vs. number of services")
    fig.subplots_adjust(left=0.16, right=0.80, top=0.88, bottom=0.20)
    ax.legend(fontsize=13, loc="upper left", bbox_to_anchor=(0.14, 0.86), bbox_transform=fig.transFigure, frameon=False)
    fig.savefig(os.path.join(OUT_DIR, "fig5_makespan_vs_cluster_size.png"), dpi=DPI)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig6: degradation under concurrent load, normalised to each path's own
# value at the lowest concurrency level -- mirrors the load-test framing of
# Rudrabhatla 2018 (choreography 1:3.6:8.2, orchestration 1:3.9:6.4 at
# 1x/5x/10x request frequency). NOTE: the concurrency sweep in this CSV
# only exercises path_d (run_concurrency_sweep is a LeaseStore-contention
# probe specific to D's election mechanism -- A and B have no lease to
# contend over, so they were never part of this sweep). This chart and its
# ratio table therefore report path_d only; it is not a three-way
# comparison like the reference paper's.
# ---------------------------------------------------------------------------
def fig6_concurrency_degradation(df: pd.DataFrame) -> None:
    sub = df[df["sweep"] == "concurrency"]
    present_paths = sorted(sub["path"].unique())

    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
    ratio_rows = []
    for path in present_paths:
        agg = sub[sub["path"] == path].groupby("concurrency_level")["makespan_ms"].mean().reset_index().sort_values("concurrency_level")
        base = float(agg["makespan_ms"].iloc[0])
        agg["ratio"] = agg["makespan_ms"] / base
        style = PATH_STYLE.get(path, dict(color="#888888", marker="o", linestyle="-"))
        ax.plot(
            agg["concurrency_level"], agg["ratio"], label=PATH_LABEL_SHORT.get(path, path),
            linewidth=LINEWIDTH, markersize=MARKERSIZE, zorder=3, **style,
        )
        for _, row in agg.iterrows():
            ratio_rows.append({"path": path, "concurrency_level": int(row["concurrency_level"]), "makespan_ms": float(row["makespan_ms"]), "ratio": float(row["ratio"])})

    ax.axhline(1.0, color="#999999", linewidth=1, linestyle=":", zorder=1)
    style_axes(ax, "Concurrency level (simultaneous rollbacks)", "Makespan ratio\n(norm. to level 1)", "Degradation under concurrent load", title_fontsize=20)
    ax.legend(fontsize=13, loc="upper left", frameon=False)

    only_note = ", ".join(PATH_LABEL_SHORT.get(p, p) for p in present_paths)
    footnote = (
        f"Concurrency sweep only covers {only_note} in this CSV (LeaseStore-contention probe specific to D's\n"
        "election) -- not a three-way comparison like the reference paper's."
    )
    fig.text(0.5, 0.015, footnote, ha="center", va="bottom", fontsize=BASE_FONT - 8, color="#555555", style="italic")

    fig.subplots_adjust(left=0.18, right=0.95, top=0.85, bottom=0.34)
    fig.savefig(os.path.join(OUT_DIR, "fig6_concurrency_degradation.png"), dpi=DPI)
    plt.close(fig)

    ratio_df = pd.DataFrame(ratio_rows)
    report_levels = [lvl for lvl in (1, 5, 10, 20) if lvl in set(ratio_df["concurrency_level"])]
    report = ratio_df[ratio_df["concurrency_level"].isin(report_levels)].sort_values(["path", "concurrency_level"])

    print("\n=== fig6: normalised makespan ratio vs. concurrency level (path_d only; see note above) ===")
    print(report.to_string(index=False))
    print()

    for path in present_paths:
        path_report = report[report["path"] == path]
        ratio_str = " : ".join(f"{r:.2f}" for r in path_report["ratio"])
        levels_str = "/".join(str(lvl) for lvl in path_report["concurrency_level"])
        REG.record(
            f"fig6: {PATH_LABEL.get(path, path)} normalised makespan ratio at concurrency levels {levels_str}",
            ratio_str,
            "makespan_ms (filtered sweep=concurrency)",
            f"groupby(concurrency_level)['makespan_ms'].mean() / value_at_level_1, reported at levels {levels_str}",
        )
    REG.record(
        "fig6: paths present in the concurrency sweep",
        ", ".join(present_paths),
        "path (filtered sweep=concurrency)",
        "sorted(df[df.sweep=='concurrency']['path'].unique()) -- only path_d, by design (see run_concurrency_sweep)",
    )


# ---------------------------------------------------------------------------
# table1: summary -- mean makespan, std, correctness rate, makespan
# relative to Path B. Bold best cell per column.
# ---------------------------------------------------------------------------
def table1_summary(df: pd.DataFrame) -> pd.DataFrame:
    # path_a, path_b, path_d must be drawn from the same population (the
    # dag_width sweep) so their means are comparable -- previously path_d
    # pooled dag_width (400 rows) together with lifo_ablation (160 rows),
    # giving it 560 rows against path_a/path_b's 400, which is exactly the
    # apples-to-oranges mixing the reviewer flagged. path_d_lifo is *only*
    # ever present in lifo_ablation, and is kept as a separately-sourced
    # ablation row rather than folded in as a fourth path.
    dag = df[df["sweep"] == "dag_width"]
    primary = dag.groupby("path")["makespan_ms"].agg(["mean", "std"]).reset_index()
    primary = primary.merge(dag.groupby("path")["correct"].mean().reset_index(), on="path")
    primary["source_sweep"] = "dag_width"

    lifo = df[(df["sweep"] == "lifo_ablation") & (df["path"] == "path_d_lifo")]
    ablation = lifo.groupby("path")["makespan_ms"].agg(["mean", "std"]).reset_index()
    ablation = ablation.merge(lifo.groupby("path")["correct"].mean().reset_index(), on="path")
    ablation["source_sweep"] = "lifo_ablation"

    table = pd.concat([primary, ablation], ignore_index=True)
    table["correctness_pct"] = table["correct"] * 100

    b_mean = float(table.loc[table["path"] == "path_b", "mean"].iloc[0])
    table["relative_to_b"] = table["mean"] / b_mean

    computation_by_col = {
        "Mean (ms)": "groupby(path)['makespan_ms'].mean()",
        "Std (ms)": "groupby(path)['makespan_ms'].std()",
        "Correct (%)": "groupby(path)['correct'].mean() * 100",
        "vs. B (x)": "mean_makespan[path] / mean_makespan[path_b]",
    }
    for _, row in table.iterrows():
        label = PATH_LABEL_SHORT[row["path"]]
        if row["path"] == "path_d_lifo":
            label = "D: LIFO ablation*"
        cols_str = f"makespan_ms / correct (filtered sweep == \"{row['source_sweep']}\")"
        for col, out_col in [("mean", "Mean (ms)"), ("std", "Std (ms)"), ("correctness_pct", "Correct (%)"), ("relative_to_b", "vs. B (x)")]:
            REG.record(f"table1: {label} -- {out_col}", float(row[col]), cols_str, computation_by_col[out_col])

    table = table[["path", "mean", "std", "correctness_pct", "relative_to_b"]]
    table.columns = ["Path", "Mean (ms)", "Std (ms)", "Correct (%)", "vs. B (x)"]
    table["Path"] = table["Path"].map(lambda p: "D: LIFO ablation*" if p == "path_d_lifo" else PATH_LABEL_SHORT[p])
    table = table.sort_values("Mean (ms)")

    footnote = "* separate sweep (lifo_ablation, n=160), not a fourth path. A/B/D rows above are dag_width only (n=400 each)."
    render_table_png(
        table,
        os.path.join(OUT_DIR, "table1_summary.png"),
        "Summary table",
        best_cols={"Mean (ms)": "min", "Std (ms)": "min", "Correct (%)": "max", "vs. B (x)": "min"},
        col_widths=[0.32, 0.18, 0.17, 0.18, 0.15],
        footnote=footnote,
    )
    write_table_markdown(table, os.path.join(OUT_DIR, "table1_summary.md"), "Table 1: Summary", footnote=footnote)
    return table


# ---------------------------------------------------------------------------
# table2: known-answer check -- expected vs measured makespan at width=1.
# ---------------------------------------------------------------------------
EXPECTED_MAKESPAN_MS = {"path_a": 1250.0, "path_b": 800.0, "path_d": 900.0}


def table2_knownanswer(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[(df["sweep"] == "dag_width") & (df["width"] == 1) & (df["path"].isin(EXPECTED_MAKESPAN_MS))]
    measured = sub.groupby("path")["makespan_ms"].mean().reset_index()
    measured["expected_ms"] = measured["path"].map(EXPECTED_MAKESPAN_MS)
    measured["deviation_pct"] = (measured["makespan_ms"] - measured["expected_ms"]) / measured["expected_ms"] * 100

    table = measured[["path", "expected_ms", "makespan_ms", "deviation_pct"]].copy()
    table.columns = ["Path", "Expected (ms)", "Measured (ms)", "Deviation (%)"]
    table["Path"] = table["Path"].map(PATH_LABEL_SHORT)
    table = table.sort_values("Path")

    for _, row in table.iterrows():
        REG.record(
            f"table2: {row['Path']} -- measured makespan at width=1 (ms)",
            float(row["Measured (ms)"]),
            "makespan_ms (filtered sweep=dag_width, width=1)",
            "groupby(path)['makespan_ms'].mean() at width=1",
        )
        REG.record(
            f"table2: {row['Path']} -- deviation from expected (%)",
            float(row["Deviation (%)"]),
            "makespan_ms",
            "(measured - expected) / expected * 100; expected hardcoded per SPEC.md's known-answer values",
        )

    render_table_png(
        table,
        os.path.join(OUT_DIR, "table2_knownanswer.png"),
        "Known-answer check (width=1)",
        best_cols={"Deviation (%)": "abs_min"},
        col_widths=[0.26, 0.25, 0.25, 0.24],
    )
    write_table_markdown(table, os.path.join(OUT_DIR, "table2_knownanswer.md"), "Table 2: Known-answer check")
    return table


# ---------------------------------------------------------------------------
# Table rendering helpers.
# ---------------------------------------------------------------------------
def render_table_png(table: pd.DataFrame, out_path: str, title: str, best_cols: dict, col_widths=None, footnote: str | None = None) -> None:
    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN))
    ax.axis("off")
    ax.set_title(title, fontsize=TITLE_FONT - 2, pad=14, wrap=True)

    display = table.copy()
    for col in display.columns:
        if col == "Path":
            continue
        display[col] = display[col].map(lambda v: f"{v:.1f}")

    n_cols = len(display.columns)
    if col_widths is None:
        # First column (Path names) needs much more room than the numeric
        # columns; split the rest evenly.
        first = 0.34
        rest = (1.0 - first) / (n_cols - 1)
        col_widths = [first] + [rest] * (n_cols - 1)

    mpl_table = ax.table(
        cellText=display.values, colLabels=display.columns, loc="center", cellLoc="center", colWidths=col_widths,
        bbox=[0.0, 0.05, 1.0, 0.72],
    )
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(BASE_FONT - 5)

    for col_name, mode in best_cols.items():
        col_idx = list(table.columns).index(col_name)
        values = table[col_name].values
        if mode == "min":
            best_mask = values == values.min()
        elif mode == "max":
            best_mask = values == values.max()
        elif mode == "abs_min":
            best_mask = np.abs(values) == np.abs(values).min()
        else:
            continue
        for row_idx in np.nonzero(best_mask)[0]:
            cell = mpl_table[(int(row_idx) + 1, col_idx)]  # +1 for header row
            cell.get_text().set_fontweight("bold")
            cell.set_facecolor("#e6f2ea")

    for col_idx in range(n_cols):
        mpl_table[(0, col_idx)].get_text().set_fontweight("bold")
        mpl_table[(0, col_idx)].set_facecolor("#f0f0f0")

    if footnote:
        fig.text(0.5, 0.02, footnote, ha="center", va="bottom", fontsize=BASE_FONT - 9, color="#555555", style="italic")

    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)


def write_table_markdown(table: pd.DataFrame, out_path: str, title: str, footnote: str | None = None) -> None:
    lines = [f"# {title}", ""]
    header = "| " + " | ".join(table.columns) + " |"
    sep = "|" + "|".join("---" for _ in table.columns) + "|"
    lines += [header, sep]
    for _, row in table.iterrows():
        cells = []
        for col in table.columns:
            v = row[col]
            cells.append(v if isinstance(v, str) else f"{v:.1f}")
        lines.append("| " + " | ".join(cells) + " |")
    if footnote:
        lines += ["", f"_{footnote}_"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_data()

    fig1_makespan_vs_width(df)
    fig2_correctness(df)
    fig3_ablation(df)
    fig4_premium(df)
    fig5_makespan_vs_cluster_size(df)
    fig6_concurrency_degradation(df)
    table1_summary(df)
    table2_knownanswer(df)

    with open(os.path.join(OUT_DIR, "key_numbers.md"), "w", encoding="utf-8") as f:
        f.write(REG.to_markdown())

    print(f"Wrote {len(REG.entries)} traced numbers and all figures/tables to {OUT_DIR}")


if __name__ == "__main__":
    main()
