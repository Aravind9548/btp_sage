# Live Demo Script

Step-by-step guide for the BTP presentation. Total demo time: ~5 minutes.

---

## Pre-demo Setup (do before the presentation)

```powershell
# 1. Open terminal in project directory
cd "C:\Users\Admin\Desktop\my dellinsperion\btp_7_saga"

# 2. Activate virtual environment
.venv\Scripts\activate

# 3. Start Docker Desktop (click the app icon, wait for it to be ready)

# 4. Start LocalStack
docker-compose -f cloud/setup/docker-compose.yml up -d

# 5. Create DynamoDB tables
python -m cloud.setup.create_resources

# 6. Verify everything is ready
python cloud_smoke_test.py
# Should show: All checks passed
```

---

## Part 1: Show the Problem (30 seconds)

**What to say:** "We have 4 microservices in a saga. When Inventory fails, we need to compensate the other 3 steps. The constraint is: Payment compensation must finish before Notification compensation starts."

```powershell
# Show the config
python -c "from saga_bench.config import SERVICES, COMPENSATION_EDGES; print('Services:', list(SERVICES.keys())); print('Dependency:', COMPENSATION_EDGES)"
```

**Expected output:**
```
Services: ['Order', 'Notification', 'Payment', 'Inventory']
Dependency: [('Payment', 'Notification')]
```

---

## Part 2: Run the Pure-Python Demo (1 minute)

**What to say:** "Let me show a single saga failure with Path D — our on-demand election approach."

```powershell
python demo.py
```

**What to point out:**
- Part 1: "See the election — one thread wins the lease, others lose. Then compensation runs in parallel respecting the dependency graph."
- Part 2: "Now watch crash recovery — orch-1 crashes mid-compensation. orch-2 detects the expired lease, re-acquires it, reads what's already done from the SagaStore, and finishes only the remaining steps. No duplicate compensation."

---

## Part 3: Show the Experiment Results (1.5 minutes)

**What to say:** "We ran 1,500+ saga runs across four experimental sweeps."

```powershell
# Show the experiment results exist
python -c "import pandas as pd; df=pd.read_csv('results/experiment_results.csv'); print(f'Total runs: {len(df)}'); print(df.groupby(['sweep','path']).agg({'makespan_ms':'mean','correct':'mean'}).round(1))"
```

**Then open the slides/ folder and show these charts:**

1. **fig1_makespan_vs_width.png** — "Path A grows linearly. Path B is flat but 0% correct. Path D is flat AND 100% correct."
2. **fig2_correctness.png** — "Choreography: 0%. Everything else: 100%."
3. **fig3_ablation.png** — "Same election, but LIFO dispatch vs graph-aware. The scheduler is what makes it fast, not the election."
4. **fig4_premium.png** — "Path D pays only ~13% premium over choreography for full correctness."

---

## Part 4: Cloud Demo on LocalStack (1.5 minutes)

**What to say:** "Now the same logic runs against real AWS services — DynamoDB for state, SNS/SQS for messaging — emulated locally via LocalStack."

```powershell
python cloud_demo.py
```

**What to point out:**
- "Part 1: Path D with DynamoDB — same election, same graph-aware dispatch, but state is in DynamoDB tables now"
- "Part 2: Crash recovery still works — lease TTL expires, re-election succeeds"
- "Part 3: Path A on DynamoDB — sequential, correct"
- "Part 4: Path B on DynamoDB — still violates ordering, as expected"
- "Look at the DynamoDB state printouts — you can see the actual String Sets stored"

**Bonus: show the DynamoDB tables directly:**
```powershell
# Show lease table state
python -c "from cloud.config import get_client, LEASE_TABLE; c=get_client('dynamodb'); print(c.scan(TableName=LEASE_TABLE)['Items'])"
```

---

## Part 5: Architecture Summary (30 seconds)

**What to say:** "The key insight is the drop-in replacement pattern. Zero changes to the coordination logic — we just swap infrastructure wrappers. The same Path A, B, and D code runs against both in-memory Python objects and cloud services."

**Show the architecture diagram artifact** (open in browser).

---

## If Asked: "What about the overhead?"

"Coordination overhead stays under 1.5% at cluster sizes up to 16. The election is modelled on DynamoDB conditional writes — `attribute_not_exists` — which is a single atomic operation in production. The real overhead would be one network round-trip, not thread contention."

## If Asked: "Why not just use orchestration?"

"Path A is correct but slow — its makespan grows linearly with DAG width because it processes compensations sequentially. At width 8, it's 2.9x slower than Path D. Path D gets the same correctness with flat scaling."

## If Asked: "How is this different from Rudrabhatla (2018)?"

"Rudrabhatla frames it as a binary choice: orchestration OR choreography. We show there's a third option — choreography for the normal path, with on-demand orchestrator election only when failure occurs. You get both the coupling benefits of choreography and the correctness of orchestration."
