# Key numbers

Every number appearing on any figure or table in `slides/`, with the
CSV column(s) and computation that produced it. Source data:
`results\experiment_results.csv`. Nothing here is hardcoded --
regenerate by rerunning `make_slides.py` against a fresh sweep.

| # | Label | Value | CSV column(s) | Computation |
|---|---|---|---|---|
| 1 | fig1: A: Orchestration mean makespan at width=1 | 1252.51 | makespan_ms (filtered sweep=dag_width, path, width=1) | groupby(path, width)['makespan_ms'].mean() |
| 2 | fig1: B: Choreography mean makespan at width=1 | 819.29 | makespan_ms (filtered sweep=dag_width, path, width=1) | groupby(path, width)['makespan_ms'].mean() |
| 3 | fig1: D: Election + graph-aware mean makespan at width=1 | 930.67 | makespan_ms (filtered sweep=dag_width, path, width=1) | groupby(path, width)['makespan_ms'].mean() |
| 4 | fig2/table1: correctness rate, B: Choreography | 0.00 | correct (filtered sweep in [dag_width, lifo_ablation]) | groupby(path)['correct'].mean() * 100 |
| 5 | fig2/table1: correctness rate, A: Orchestration | 100.00 | correct (filtered sweep in [dag_width, lifo_ablation]) | groupby(path)['correct'].mean() * 100 |
| 6 | fig2/table1: correctness rate, D: Election + graph-aware | 100.00 | correct (filtered sweep in [dag_width, lifo_ablation]) | groupby(path)['correct'].mean() * 100 |
| 7 | fig2/table1: correctness rate, D (naive LIFO ablation) | 100.00 | correct (filtered sweep in [dag_width, lifo_ablation]) | groupby(path)['correct'].mean() * 100 |
| 8 | fig3: dependency-aware makespan at width=8 | 907.28 | makespan_ms (sweep=lifo_ablation, path=path_d) | groupby(width)['makespan_ms'].mean() at width=8 |
| 9 | fig3: LIFO makespan at width=8 | 2668.96 | makespan_ms (sweep=lifo_ablation, path=path_d_lifo) | groupby(width)['makespan_ms'].mean() at width=8 |
| 10 | fig3: LIFO-vs-graph-aware gap at width=8 (ms) | 1761.68 | makespan_ms | lifo_mean - dependency_aware_mean at max width |
| 11 | fig3: LIFO-vs-graph-aware gap at width=8 (%) | 194.17 | makespan_ms | gap_ms / dependency_aware_mean * 100 |
| 12 | fig4: mean D-over-B makespan premium (ms), averaged over DAG widths 1-8 | 107.12 | makespan_ms (sweep=dag_width, path in [path_b, path_d]) | mean over width of (D_mean_makespan - B_mean_makespan) |
| 13 | fig4: mean D-over-B makespan premium (%), averaged over DAG widths 1-8 | 13.29 | makespan_ms | mean over width of ((D_mean - B_mean) / B_mean * 100) |
| 14 | fig4 (bottom): B: Choreography correctness rate (flat across widths) | 0.00 | correct (sweep=dag_width) | groupby(path, width)['correct'].mean() * 100, averaged over width |
| 15 | fig4 (bottom): D: Election + graph-aware correctness rate (flat across widths) | 100.00 | correct (sweep=dag_width) | groupby(path, width)['correct'].mean() * 100, averaged over width |
| 16 | fig5: A: Orchestration slope (ms per added service) | 201.14 | makespan_ms (filtered sweep=cluster_size) | np.polyfit(cluster_size, groupby(path, cluster_size)['makespan_ms'].mean(), deg=1)[0] |
| 17 | fig5: B: Choreography slope (ms per added service) | 1.47 | makespan_ms (filtered sweep=cluster_size) | np.polyfit(cluster_size, groupby(path, cluster_size)['makespan_ms'].mean(), deg=1)[0] |
| 18 | fig5: D: Election + graph-aware slope (ms per added service) | -1.58 | makespan_ms (filtered sweep=cluster_size) | np.polyfit(cluster_size, groupby(path, cluster_size)['makespan_ms'].mean(), deg=1)[0] |
| 19 | fig6: D: Election + graph-aware normalised makespan ratio at concurrency levels 1/5/10/20 | 1.00 : 1.01 : 1.01 : 1.01 | makespan_ms (filtered sweep=concurrency) | groupby(concurrency_level)['makespan_ms'].mean() / value_at_level_1, reported at levels 1/5/10/20 |
| 20 | fig6: paths present in the concurrency sweep | path_d | path (filtered sweep=concurrency) | sorted(df[df.sweep=='concurrency']['path'].unique()) -- only path_d, by design (see run_concurrency_sweep) |
| 21 | table1: A: Orchestration -- Mean (ms) | 1954.65 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].mean() |
| 22 | table1: A: Orchestration -- Std (ms) | 460.26 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].std() |
| 23 | table1: A: Orchestration -- Correct (%) | 100.00 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['correct'].mean() * 100 |
| 24 | table1: A: Orchestration -- vs. B (x) | 2.43 | makespan_ms / correct (filtered sweep == "dag_width") | mean_makespan[path] / mean_makespan[path_b] |
| 25 | table1: B: Choreography -- Mean (ms) | 805.91 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].mean() |
| 26 | table1: B: Choreography -- Std (ms) | 11.17 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].std() |
| 27 | table1: B: Choreography -- Correct (%) | 0.00 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['correct'].mean() * 100 |
| 28 | table1: B: Choreography -- vs. B (x) | 1.00 | makespan_ms / correct (filtered sweep == "dag_width") | mean_makespan[path] / mean_makespan[path_b] |
| 29 | table1: D: Graph-aware -- Mean (ms) | 913.03 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].mean() |
| 30 | table1: D: Graph-aware -- Std (ms) | 18.58 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['makespan_ms'].std() |
| 31 | table1: D: Graph-aware -- Correct (%) | 100.00 | makespan_ms / correct (filtered sweep == "dag_width") | groupby(path)['correct'].mean() * 100 |
| 32 | table1: D: Graph-aware -- vs. B (x) | 1.13 | makespan_ms / correct (filtered sweep == "dag_width") | mean_makespan[path] / mean_makespan[path_b] |
| 33 | table1: D: LIFO ablation* -- Mean (ms) | 1965.02 | makespan_ms / correct (filtered sweep == "lifo_ablation") | groupby(path)['makespan_ms'].mean() |
| 34 | table1: D: LIFO ablation* -- Std (ms) | 461.83 | makespan_ms / correct (filtered sweep == "lifo_ablation") | groupby(path)['makespan_ms'].std() |
| 35 | table1: D: LIFO ablation* -- Correct (%) | 100.00 | makespan_ms / correct (filtered sweep == "lifo_ablation") | groupby(path)['correct'].mean() * 100 |
| 36 | table1: D: LIFO ablation* -- vs. B (x) | 2.44 | makespan_ms / correct (filtered sweep == "lifo_ablation") | mean_makespan[path] / mean_makespan[path_b] |
| 37 | table2: A: Orchestration -- measured makespan at width=1 (ms) | 1252.51 | makespan_ms (filtered sweep=dag_width, width=1) | groupby(path)['makespan_ms'].mean() at width=1 |
| 38 | table2: A: Orchestration -- deviation from expected (%) | 0.20 | makespan_ms | (measured - expected) / expected * 100; expected hardcoded per SPEC.md's known-answer values |
| 39 | table2: B: Choreography -- measured makespan at width=1 (ms) | 819.29 | makespan_ms (filtered sweep=dag_width, width=1) | groupby(path)['makespan_ms'].mean() at width=1 |
| 40 | table2: B: Choreography -- deviation from expected (%) | 2.41 | makespan_ms | (measured - expected) / expected * 100; expected hardcoded per SPEC.md's known-answer values |
| 41 | table2: D: Graph-aware -- measured makespan at width=1 (ms) | 930.67 | makespan_ms (filtered sweep=dag_width, width=1) | groupby(path)['makespan_ms'].mean() at width=1 |
| 42 | table2: D: Graph-aware -- deviation from expected (%) | 3.41 | makespan_ms | (measured - expected) / expected * 100; expected hardcoded per SPEC.md's known-answer values |
