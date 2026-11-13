# Table 1: Summary

| Path | Mean (ms) | Std (ms) | Correct (%) | vs. B (x) |
|---|---|---|---|---|
| B: Choreography | 805.9 | 11.2 | 0.0 | 1.0 |
| D: Graph-aware | 913.0 | 18.6 | 100.0 | 1.1 |
| A: Orchestration | 1954.6 | 460.3 | 100.0 | 2.4 |
| D: LIFO ablation* | 1965.0 | 461.8 | 100.0 | 2.4 |

_* separate sweep (lifo_ablation, n=160), not a fourth path. A/B/D rows above are dag_width only (n=400 each)._
