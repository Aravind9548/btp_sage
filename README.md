# Saga Compensation Coordination Benchmark

Pure-Python (3.11+) benchmark comparing four ways to coordinate rollback of
a failed distributed saga: orchestration (Path A), naive choreography
(Path B), and this project's contribution -- choreography with on-demand
leader election and a dependency-graph-aware compensation scheduler (Path
D, plus a naive-LIFO ablation of the same election). See `SPEC.md` for the
full build spec.

No network calls, no cloud SDKs, no Docker. Services are Python classes;
the event bus is an in-process dict + thread pool; the lease store is a
dict + mutex. Everything is deterministic (no RNG anywhere); real
`time.sleep()` is used to simulate service work, so individual wall-clock
timestamps carry a little OS thread-scheduling jitter, but aggregate
statistics and the ordering between paths are stable run to run.

## Setup

```
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Running things

- **Tests:** `.venv\Scripts\python.exe -m pytest tests/ -v` (32 tests, ~35s)
- **Demo** (single saga, verbose, Path D, ~3s): `.venv\Scripts\python.exe demo.py`
- **Full experiment sweep** (~2 min, must be under 5 min):
  `.venv\Scripts\python.exe run_experiments.py`
  Writes `results/experiment_results.csv`, `results/events.csv`, and four
  charts to `results/`.
- **Slide assets** (figures/tables/key_numbers.md for the deck, reads the
  CSV above, never re-runs the experiment): `.venv\Scripts\python.exe make_slides.py`
  Writes six figures (`fig1`-`fig6`), two tables (`table1_summary`,
  `table2_knownanswer`, each as `.png` + `.md`), and `key_numbers.md` to
  `slides/` -- see "Slide deck assets" below for what each one is.

## Layout

- `saga_bench/config.py` -- service durations, the compensation dependency
  graph, DAG-width-sweep synthetic step config. Single source of truth.
- `saga_bench/event_bus.py`, `event_log.py`, `saga_store.py`,
  `lease_store.py`, `fault_injector.py` -- Stage 1 harness.
- `saga_bench/graph.py` -- the compensation DAG as data, plus
  `verify_rollback`, which is the only thing that decides correctness (it
  reads the event log, never a scheduler's intentions).
- `saga_bench/services.py` -- the four services; `compensate()` is
  idempotent via `SagaStore.mark_compensated`, which doubles as the
  idempotency key everywhere re-election safety matters.
- `saga_bench/paths/orchestration.py` (A), `choreography.py` (B),
  `path_d.py` (D + LIFO ablation).
- `saga_bench/experiment/` -- scenario builder, sweep runner, charts.
- `demo.py`, `run_experiments.py` -- entry points.

## Key design decisions worth knowing before reading the code

**Forward step order is `Order, Notification, Payment, Inventory`, not the
spec table's listed order.** The compensation constraint is
Payment-must-finish-before-Notification. Path A compensates in strict
reverse of forward order with zero graph awareness -- for that to be
correct, Notification has to come *before* Payment in the forward chain,
so that reversing puts Payment first. This is deliberate and documented in
`config.py`: it's what makes Path A "correct by construction" *for this
particular hand-picked schedule*, not correct in general. Reorder those
two steps and Path A breaks; Path D wouldn't, because it derives ordering
from the graph itself rather than from a lucky schedule.

**Failures stop the forward chain, they don't happen after the fact.**
`FaultInjector.should_fail(saga_id, step)` is checked immediately before a
step would run; if true, that step and everything after it never executes,
and only what already completed needs compensating. The main experiment
always fails at `Inventory` (last in the forward order), so every other
step -- including both ends of the Payment/Notification edge -- has
already completed and needs compensating on every single injected
failure.

**`verify_rollback`'s edge check is scoped to what actually needed
compensating.** For edge `(a, b)`: if `b` never got compensated, the edge
wasn't exercised (vacuously fine). If `b` did get compensated but `a`
never even started compensating, `a` was never part of this rollback (it
never completed forward, e.g. a step downstream of where the fault fired)
-- so there's nothing for `b` to have waited for. Only when `a` started
compensating but didn't finish before `b` started is it a genuine
violation. This is what lets the same function correctly judge both a
full four-step rollback and a partial one.

**Every service run gets its own `EventBus`, but shares `SagaStore` and
`LeaseStore` with the rest of its sweep.** An earlier version shared one
`EventBus` (with a fixed-size internal thread pool) across an entire
sweep, which meant hundreds of concurrently-running Path B sagas queued
behind each other for that bus's worker threads -- inflating Path B's
measured makespan with a benchmark-plumbing artifact instead of anything
about choreography itself. `EventBus` topics are already saga_id-scoped,
so a fresh bus per saga run is behaviorally identical and removes the
cross-talk. `SagaStore`/`LeaseStore` sharing is intentional: the
concurrency sweep specifically needs one shared lease-store mutex to
contend on.

**The DAG-width and cluster-size sweeps process one width/size at a time**
(submit that size's jobs, wait for all of them, then move to the next),
rather than firing all widths/sizes at the thread pool simultaneously.
Coordination overhead is a small time-over-time ratio; letting every
size's jobs race for the same worker pool at once let unrelated jobs'
scheduling noise leak into a given size's measurement (observed initially
as a wildly noisy chart 4, spiking to 27%). Isolating each size fixed it.

## Headline results (from the last `run_experiments.py` run)

**Lead with this framing, not "we're fastest":** Path D pays a small,
bounded latency premium over choreography (~93-120ms, ~11-15%, flat
across DAG width 1-8) and gets full correctness for it, while
orchestration pays a large and growing one (1.5x at width 1, 2.9x by
width 8) for the same correctness. The "why not just use choreography"
question answers itself the moment the correctness column is on screen
next to that gap.

| Path | Mean makespan | Correctness | Mean overhead ratio |
|---|---|---|---|
| A: Orchestration | ~1955 ms, grows linearly with DAG width | 100% | 0 |
| B: Choreography | ~806 ms, flat regardless of width | **0%** | 0 |
| D: Election + graph-aware | ~912 ms, flat regardless of width | 100% | under 1.5% at almost every cluster size |
| D (naive LIFO ablation) | grows linearly with width, like A | 100% | similar to D |

**Known-answer check** (width=1, averaged over 50 runs from the full
sweep): A=1252.5ms (0.2% off 1250), B=819.3ms (2.4% off 800), D=930.7ms
(3.4% off 900) -- see `slides/table2_knownanswer.png` for the exact
figures from the current CSV. This confirms the EventBus fix (below)
applies uniformly: Path A never had any internal thread pool to contend
on, and Path D's election/dispatch executors were always created fresh
per saga run even before the fix, so D never benefited from an isolation
that B lacked -- the fix only ever removed an artifact that only ever
hurt B.

### Path B's 0% correctness: deterministic, and not for the reason it first looks like

It would be a mistake to present "choreography violated ordering in 100%
of trials" as an empirical rate -- with fixed, non-random configuration,
it's arithmetic, not measurement. The honest question is *why* it's
deterministic, and the first-pass answer ("Notification's 100ms
compensation is simply always shorter than Payment's 800ms") turns out to
be wrong, not just informal:

- `verify_rollback`'s edge check is `finished[Payment] > started[Notification]`.
  Notification's *own* duration never appears in that condition -- only
  when it *starts* matters, not how long it takes. Sweeping Notification's
  compensate duration from 1ms to 3200ms (Payment fixed at 800ms) changes
  nothing: 0% correctness at every value. Duration racing was never the
  mechanism.
- Sweeping Payment's duration instead (0ms to 800ms, Notification fixed at
  100ms) *also* shows 0% at every value, including Payment=0ms -- which
  ruled out a simple race entirely. Measuring the raw dispatch showed why:
  Notification's reactor consistently starts 0.3-0.9ms before Payment's,
  every single trial, not as jitter but systematically. `EventBus`
  dispatches subscribers in subscription order, and subscription order
  here follows forward execution order (Order, Notification, Payment) --
  so Notification's thread is always created and scheduled first. Given
  that, the violation isn't probabilistic at all: Payment's finish can
  never precede its own start, and its start already follows
  Notification's start. It's logically guaranteed, not merely likely.
- To find where a genuine crossover exists, I reran the sweep with
  subscription order reversed (Payment dispatched before Notification),
  isolating the scheduling artifact from the underlying "everyone reacts
  to one event, with no ordering" choreography design. That *does* produce
  a real curve: 100% correct at Payment=0ms, 66.7% at 0.01ms, 56.7% at
  0.1ms, 0% by 1ms and beyond. The crossover is real, but it lives entirely
  in a sub-millisecond band that has no relationship to real service
  behavior -- a real refund takes hundreds of milliseconds to seconds, not
  fractions of one.

**The conclusion that survives scrutiny:** for any realistic compensation
duration, naive choreography's ordering violation is guaranteed -- not
because of an implementation quirk in this harness's dispatch order (that
effect is real but reinforcing, not load-bearing), and not because of how
the four durations in this benchmark happen to compare, but because
choreography has no mechanism to make one compensation wait on another at
all. There is no realistic duration configuration where it would resolve
correctly.

The LIFO ablation isolates where Path D's speed comes from: LIFO uses the
exact same election mechanism as the dependency-aware scheduler and is
just as correct (100%), but because it never parallelizes independent
compensations, its makespan grows with width just like Path A's. The
scheduler, not the election, is what buys the flat makespan.

The coordination-overhead-vs-cluster-size chart stays under ~1.5% at
almost every cluster size (one batch showed a transient ~7% average,
apparently a momentary system load spike during that specific wave rather
than a trend with size -- see the concurrency-tuning finding below for
why this number is sensitive to background load at all). Overhead is
implemented as N real OS threads racing `try_acquire` plus a nested
dispatch pool, so it is not literally zero the way a production
implementation backed by a single atomic conditional write (e.g.
DynamoDB's `attribute_not_exists`, which `LeaseStore.try_acquire` is
modelled on) would be -- but on this machine, at a sane concurrency
setting, it stays small and does not visibly trend upward with cluster
size out to 16 services.

## First measurement artifact: EventBus contention (worth its own slide)

The `EventBus` bug is worth presenting on its own, separately from the
result charts: it demonstrates the harness was audited, not just run.
Summary: an earlier version shared one `EventBus` instance -- and its
fixed 32-worker internal thread pool -- across every concurrently-running
saga in a sweep. Since `EventBus` topics are already saga_id-scoped,
sharing the object bought nothing, but its bounded pool became a point of
contention: hundreds of concurrent Path B sagas queued behind each other
for the same 32 worker threads, inflating Path B's measured makespan from
~800ms to ~5270ms -- a 6x artifact of the benchmark's own plumbing, not of
choreography. It was caught by noticing Path B's numbers moved when the
*outer* sweep concurrency was raised (200 workers) despite Path B's own
logic being unchanged -- a red flag that some resource was being shared
across unrelated saga runs. The fix (a fresh `EventBus` per saga run) is
described above; the known-answer check confirms it applies uniformly
across all three paths, not just the one that was visibly broken.

## Second measurement artifact: outer sweep concurrency was oversubscribed

While re-checking everything end to end, a second harness artifact turned
up, worse than it first looked. `run_experiments.py` ran the whole sweep
against one `ThreadPoolExecutor(max_workers=200)` shared by every saga in
every sweep. This machine has 12 logical cores. 200 outer worker threads,
each potentially spawning 1-2 more nested threads inside Path D's
election and dispatch, means peak concurrent OS threads in the high
hundreds racing for 12 cores -- a ~15-20x oversubscription. The effect
wasn't just noise: at 200 workers, DAG width 8's mean makespan for Path D
came out at ~1800ms against a ~950-1070ms baseline at every other width
in the same run -- a real ~2x regime shift, not a wide error bar -- and
the coordination-overhead-ratio distribution showed individual runs as
high as 54%, with per-cluster-size means themselves ranging 6-15% with
comparably large standard deviations (e.g. cluster size 13: mean 15%, std
15%). None of this was random: it reproduced across reruns as "whichever
batch of jobs happens to be competing for CPU time gets slower," which is
exactly what thread oversubscription predicts.

Dropping `max_workers` from 200 to 48 (still 4x oversubscribed relative
to 12 cores, but nowhere near 17x) fixed it: the width-8 regime shift
disappeared (back in line with every other width), coordination overhead
dropped to consistently under 1.5% at nearly every cluster size, and
total wall time was *unchanged* (~130s either way) -- confirming that the
extra 152 threads were pure contention, not throughput. This is now the
default in `run_experiments.py`. **Lesson for the "why was your overhead
number different last time" question:** an earlier draft of this README
reported overhead climbing to 3-4% "with cluster size" based on a run at
higher concurrency; that trend doesn't reproduce at a sane concurrency
setting, which is itself the more interesting finding -- the number was
measuring this benchmark's own thread-pool contention, not anything about
Path D's coordination design. All of the correctness numbers (100% / 0% /
100% / 100%) were completely unaffected throughout, since correctness is
structurally determined by the graph and the completed-steps set, never
by timing.

## Slide deck assets

`make_slides.py` reads only `results/experiment_results.csv` -- it never
touches `saga_bench/` and never re-runs the experiment -- and writes to
`slides/`:

| File | What it shows |
|---|---|
| `fig1_makespan_vs_width.png` | Makespan vs. DAG width, all three paths. Headline figure. |
| `fig2_correctness.png` | Correctness rate by path, worst to best. |
| `fig3_ablation.png` | Path D: dependency-aware scheduler vs. naive LIFO, same election. |
| `fig4_premium.png` | The "bounded premium" figure: B vs. D makespan and correctness, stacked. |
| `fig5_makespan_vs_cluster_size.png` | Makespan vs. number of services (4-16), with per-path slope annotated. Framed to sit next to Rudrabhatla (2018, IJACSA)'s microservice-count sweep. |
| `fig6_concurrency_degradation.png` | Makespan ratio vs. concurrency level, normalised to level 1. **Path D only** -- see caveat below. |
| `table1_summary.png` / `.md` | Mean/std makespan, correctness, and ratio-to-B per path. A/B/D rows come from the `dag_width` sweep only (n=400 each, comparable populations); the LIFO ablation is a separate row drawn from `lifo_ablation` (n=160), marked with `*` rather than folded in as a fourth path. |
| `table2_knownanswer.png` / `.md` | Expected vs. measured makespan at width=1, per path. |
| `key_numbers.md` | Every number on every figure/table, traced to its CSV column(s) and computation. Nothing in `slides/` is hardcoded. |

**fig6 caveat:** `run_concurrency_sweep` in `saga_bench/experiment/runner.py`
is a `LeaseStore`-contention probe specific to Path D's election mechanism
-- Paths A and B have no lease to contend over, so the CSV's `concurrency`
sweep only ever contains `path_d` rows. fig6 is honest about this (it says
so on the chart), but it is **not** a three-way comparison like the
degradation-ratio figures in Rudrabhatla (2018) -- there is no A/B data in
this CSV to compare against. D's own ratio stays essentially flat (1.00 :
1.01 : 1.01 : 1.01 at concurrency 1/5/10/20), which is a good result for D
in isolation, but producing the actual cross-path comparison would mean
extending the sweep to drive A and B too, which means touching
`saga_bench/` and re-running -- deliberately not done here.

## Cloud Layer (LocalStack)

A `cloud/` package provides drop-in AWS-backed replacements for every
infrastructure component. The coordination logic in `saga_bench/paths/`
is **completely unchanged** — cloud wrappers implement the same interface
and are injected via the existing `**kwargs` on each path function.

### Components

| Python class | In-memory original | AWS service |
|---|---|---|
| `cloud.dynamo_lease_store.DynamoLeaseStore` | `LeaseStore` (dict + mutex) | DynamoDB conditional puts |
| `cloud.dynamo_saga_store.DynamoSagaStore` | `SagaStore` (dict of sets) | DynamoDB String Sets |
| `cloud.dynamo_event_log.DynamoEventLog` | `EventLog` (append-only list) | DynamoDB composite key |
| `cloud.sns_sqs_event_bus.SnsSqsEventBus` | `EventBus` (ThreadPool) | SNS + SQS |
| `cloud.kafka_event_bus.KafkaEventBus` | `EventBus` (ThreadPool) | Apache Kafka |

### Quick start

```powershell
# 1. Start LocalStack (requires Docker Desktop running)
docker-compose -f cloud/setup/docker-compose.yml up -d

# 2. Create DynamoDB tables and SNS topic
.venv\Scripts\python.exe -m cloud.setup.create_resources

# 3. Verify
.venv\Scripts\python.exe cloud_smoke_test.py

# 4. Run cloud demo (all 4 parts)
.venv\Scripts\python.exe cloud_demo.py
```

Or use the one-command setup: `.venv\Scripts\powershell cloud_setup.ps1`

### What the cloud demo shows

- **Part 1:** Path D on DynamoDB — election + graph-aware dispatch
- **Part 2:** Crash recovery — orch-1 crashes, lease expires, orch-2 re-elects
- **Part 3:** Path A on DynamoDB — sequential compensation
- **Part 4:** Path B on DynamoDB — ordering violation (0% correctness, as expected)
- **Part 5:** Path B with Kafka EventBus — same choreography, Kafka as message broker

After each part, DynamoDB table contents are printed to show real cloud state.

### Requirements

- Docker Desktop (for LocalStack 3.8.1 + Kafka 3.7 containers)
- `boto3`, `kafka-python-ng` (in `requirements.txt`)
- No AWS account or credits needed

## Presentation Assets

| Asset | Location |
|---|---|
| Slide charts/tables | `slides/fig1`-`fig6` + `table1`/`table2` (PNG + MD) |
| Key numbers with CSV tracing | `slides/key_numbers.md` |
| Related work comparison | `slides/related_work.md` |
| Architecture diagrams | `architecture_diagrams.html` (also published as artifact) |
| HTML report with all metrics | `report.html` (also published as artifact) |
| Live demo script | `DEMO_SCRIPT.md` |

## Deliberately out of scope

Per `SPEC.md`: Path C (static hybrid), Path E (Xue et al. 2021's
mechanism, pending the full paper text).
