# Build Spec: Saga Compensation Coordination Benchmark

**How to use this file:** Put it in an empty repo as `SPEC.md`, open Claude Code there, and work through the stages one at a time. Do not paste the whole file as a single prompt. At each stage, paste that stage's section, verify the checkpoint passes, then move on. Whoever owns a path should be able to explain their code without reading it.

---

## Project context

We are comparing four coordination strategies for rolling back a failed distributed transaction (a Saga) in a microservice system. When a step fails, the already-completed steps must be undone via compensating actions. The question is who coordinates those compensations, and how fast and how correctly they complete.

We are measuring:

1. **Compensation makespan** — failure detected to last compensation acknowledged
2. **Correctness rate** — fraction of rollbacks that respect ordering constraints between compensations
3. **Coordination overhead ratio** — time spent coordinating divided by total rollback time

The headline result we expect: choreography is fast but violates ordering constraints, orchestration is correct but serializes everything, and our approach (Path D) is both fast and correct.

---

## Hard constraints

- **Pure Python 3.11+. No AWS, no LocalStack, no Docker, no network calls, no cloud SDKs.** Services are Python classes; the event bus is an in-process dict plus a thread pool; the lease store is a dict plus a mutex. This is deliberate: cloud latency variance would swamp the millisecond-scale effects being measured.
- Dependencies limited to the standard library plus `pandas` and `matplotlib` for the final charts. Nothing else without asking.
- Everything must be **deterministic and repeatable** — fixed seeds, fixed fault injection. Rerunning the full experiment must produce the same numbers.
- Service work is simulated with `time.sleep()`. There is no real business logic and none should be invented.
- The full experiment sweep must complete in **under five minutes**, so results can be regenerated quickly when a bug is found late.
- Write `pytest` tests as you go. Every stage has a verification checkpoint that must pass before the next stage starts.

---

## Domain model

Four services, each with an `execute()` and a `compensate()` method. Both just sleep for a configured duration and emit a structured log row.

| Service | Execute | Compensate | Compensating action |
|---|---|---|---|
| Order | 100 ms | 150 ms | Cancel order |
| Payment | 300 ms | 800 ms | Refund |
| Inventory | 200 ms | 200 ms | Release reservation |
| Notification | 50 ms | 100 ms | Send cancellation notice |

These durations are a stated modelling assumption, not measurements. Keep them in one config module so they can be changed in a single place.

### Compensation dependency graph

This is the most important part of the spec. Compensations are **not** all independent:

```
refund(Payment)  ──must complete before──>  cancellation_notice(Notification)
release(Inventory)   independent
cancel(Order)        independent
```

**Rationale for the constraint:** the customer must not receive a cancellation notice before the money is actually back. Real systems have constraints like this and they are exactly what naive parallel compensation gets wrong.

A rollback is **correct** if and only if every edge in this graph is respected — i.e. `refund` finished before `cancellation_notice` started. Any rollback that violates an edge is logged as incorrect.

The graph must be data, not hardcoded control flow, so DAG width can be swept later.

---

## Stage 1 — Harness

Build only this. No paths, no experiment, no charts yet.

- `EventBus` — topic to subscriber callbacks, dispatched on a thread pool so subscribers run concurrently. Support publish and subscribe.
- `SagaStore` — per `saga_id`, tracks which steps completed and which have been compensated. Thread-safe.
- `LeaseStore` — `try_acquire(saga_id, owner) -> bool` implementing an atomic put-if-absent under a mutex, plus a TTL after which the lease expires and can be re-acquired. This models a DynamoDB conditional write with `attribute_not_exists`; keep that comparison in a code comment.
- `EventLog` — append-only structured rows: `saga_id, path, event, step, timestamp_ms, thread_id`. Dumps to CSV.
- `FaultInjector` — config-driven: which step fails, for which saga IDs. Fully deterministic.

**Checkpoint:** tests prove that when 10 threads race `try_acquire` on the same `saga_id`, exactly one succeeds; that the lease becomes re-acquirable after its TTL; and that the event log preserves ordering with correct timestamps under concurrent writes.

---

## Stage 2 — Services and graph

- The four services above, driven by the duration config.
- The compensation dependency graph as a data structure, with helpers for topological order, critical path length, and "which compensations are safe to run now given what has finished."
- A `verify_rollback(event_log, saga_id) -> bool` function that checks every graph edge was respected in the actual recorded timeline. This is how correctness gets scored, so it must read from the log, not from the scheduler's intentions.

**Checkpoint:** `verify_rollback` returns `False` for a hand-constructed log where the notification precedes the refund, and `True` for a valid one.

---

## Stage 3 — Path A (orchestration baseline)

A single coordinator function calling services in sequence. On failure, it runs compensations in strict reverse order, one at a time.

Deliberately **not** using Step Functions or any cloud service — a plain sequential coordinator has identical semantics for what is being measured.

**Checkpoint:** injecting a Payment failure produces a rollback whose makespan is approximately the sum of all compensation durations, and `verify_rollback` returns `True`.

---

## Stage 4 — Path B (choreography baseline)

Each service subscribes to the previous service's success event. On failure, a `CompensationNeeded` event is published and **every service that completed a step reacts independently and immediately**, running its own compensation concurrently with the others.

**Critical instruction: do not make this path correct.** Path B has no coordinator and therefore no knowledge of the dependency graph. It must be able to send the cancellation notice before the refund has completed. That failure is the experimental result being measured, not a bug. Do not add ordering logic, waits, or checks to "fix" it.

**Checkpoint:** Path B's makespan is approximately the *maximum* compensation duration rather than the sum, and `verify_rollback` returns `False` on a meaningful fraction of runs.

---

## Stage 5 — Path D (the contribution)

Normal operation is identical to Path B — fully choreographed, no coordinator.

On failure:

1. A `CompensationNeeded` event is published.
2. All candidate services race to acquire the lease for that `saga_id` via `LeaseStore.try_acquire`. Exactly one wins and becomes the temporary orchestrator for this saga instance only.
3. The winner reads `SagaStore` for which steps completed, builds the compensation sub-graph for exactly those steps, and dispatches them **along the critical path** — independent compensations concurrently, dependent ones in order.
4. Before dispatching any compensation, it writes a `compensated` marker for that step, and each compensating action takes an idempotency key. A re-elected orchestrator must never re-run a compensation that already ran.
5. The lease is released on completion, or expires by TTL. TTL expiry triggers re-election so a mid-rollback coordinator crash is recoverable.
6. After the rollback, no coordinator exists. The next saga runs pure choreography again.

Also implement a **naive LIFO variant behind the same election**, switchable by config flag. This isolates how much of the benefit comes from the scheduler versus the election, and is reported as an ablation.

**Checkpoint:** Path D's makespan is approximately the critical path length (noticeably less than Path A's sum, slightly more than Path B's max); `verify_rollback` returns `True` on every run; and a test that kills the elected orchestrator mid-rollback shows re-election completing the rollback with no compensation executed twice.

---

## Stage 6 — Experiment runner and charts

- Sweep **DAG width from 1 to 8** by adding independent compensations to the graph, holding the constrained edge fixed.
- 50 saga instances per path per width, with injected failures.
- Also sweep concurrent failure rate (1 to 20 simultaneous rollbacks) to test lease contention, and cluster size (4 to 16 services) to show coordination overhead stays flat.
- Emit one tidy CSV of all runs, then produce:
  - **Chart 1:** makespan versus DAG width, one line per path. This is the headline figure.
  - **Chart 2:** correctness rate per path, as a table and a bar chart.
  - **Chart 3:** the LIFO-versus-dependency-aware ablation within Path D.
  - **Chart 4:** coordination overhead ratio versus cluster size.
- A summary table printed to stdout: path, mean makespan, correctness rate, overhead ratio.
- A `demo.py` that runs a **single** saga on Path D with verbose output — failure injected, election won, compensations firing in parallel, lease expiring — in under 30 seconds, from one command, with no internet. This is what gets run live in the presentation.

**Checkpoint:** `python run_experiments.py` completes in under five minutes and writes all four charts plus the CSV. Running it twice produces identical numbers.

---

## Report honestly

If Path D loses to Path B on raw makespan at low DAG widths, that is a real result — report it and let the charts show where the crossover is. Do not tune parameters to make Path D win everywhere. A stated break-even point is a stronger result than a uniform win, because it demonstrates the system is understood rather than merely run once.

---

## Deliberately out of scope

- **Path C (static hybrid)** — a baseline nobody will attack, not worth the person-hours.
- **Path E (base paper's mechanism)** — will be added only once the full text of Xue et al. 2021 is obtained. Do not implement a guessed version of someone else's mechanism.
- **AWS or LocalStack deployment** — possible future work, not part of this build.
