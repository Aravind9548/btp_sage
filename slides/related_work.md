# Related Work Comparison

## Garcia-Molina & Salem (1987)

Introduced sagas as sequences of transactions with compensating actions — the foundational model. Their work assumes a single-database system with a central log; it does not address coordination strategy selection in distributed microservices. Path D builds on their compensation model but adds on-demand leader election and a dependency-graph-aware parallel scheduler — mechanisms that have no counterpart in the original formulation.

## Rudrabhatla (2018, IJACSA Vol 9 No 8)

Compared event choreography and orchestration for saga implementation in microservice architectures, including a service-count sweep. The paper frames the choice as binary — either a central coordinator or fully decoupled event reactions — and evaluates coupling, complexity, and scalability qualitatively. **Path D demonstrates this is a false dichotomy:** choreography during normal operation with a temporary, elected orchestrator only during failure gives the coupling benefits of choreography and the correctness guarantees of orchestration simultaneously.

## Xue, Deng, Liu & Yan (2021, Computer Networks)

Analyze data dependencies among composite microservices and build coordination mechanisms on the saga method to reach consensus at runtime without a permanent coordinator. Closest to Path D conceptually. However, our work adds three concrete mechanisms they do not benchmark:
1. Competitive lease acquisition for orchestrator election modelled on DynamoDB conditional writes
2. A dependency-graph-aware parallel compensation scheduler (proven by ablation to be the key factor — not the election)
3. Lease-TTL-based crash recovery with idempotent re-election

## Aydın & Çebi (2022, IEEE ICECET) and Dürr, Lichtenthäler & Wirtz (2022, CLOSER)

Both compare choreography and orchestration saga implementations. Aydın & Çebi focus on data consistency with NoSQL databases; Dürr et al. propose a qualitative criteria catalog evaluating four saga technologies. Neither provides a quantitative latency/correctness benchmark with controlled fault injection.

## Our Contribution (Path D)

Path D's novelty lies in three contributions no prior work combines:

| Contribution | Evidence |
|---|---|
| Zero-overhead normal operation (pure choreography, no coordinator) | Coordinator elected only on failure |
| DAG-aware parallel compensation scheduler | Ablation: LIFO with same election is 194% slower at width 8 |
| Cloud-validated architecture | Drop-in mapping to DynamoDB + SNS/SQS via LocalStack |

**Quantitative gap filled:** 1,500+ saga runs across four sweeps (DAG width, concurrency, cluster size, ablation), with deterministic fault injection and a correctness verifier that reads only the event log, never a scheduler's intentions.

## Sources

- Garcia-Molina & Salem (1987) — Princeton Tech Report
- Rudrabhatla (2018) — IJACSA Vol 9 No 8
- Xue et al. (2021) — Computer Networks
- Aydın & Çebi (2022) — IEEE ICECET
- Dürr et al. (2022) — CLOSER / Scitepress
