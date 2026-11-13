"""Saga Compensation Benchmark — Web Dashboard.

Multi-page Flask app for demonstrating and presenting the project.

Usage:
    python web_app.py
    Open http://localhost:5000
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory

PROJECT = Path(__file__).resolve().parent
SLIDES = PROJECT / "slides"

# On Vercel there is no Docker, so LocalStack and Kafka are unreachable by
# definition. Probing them would add a 2s timeout to every single request.
SERVERLESS = bool(os.environ.get("VERCEL"))

app = Flask(
    __name__,
    template_folder=str(PROJECT / "web"),
    static_folder=str(PROJECT / "web" / "static"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _use_cloud() -> bool:
    if SERVERLESS:
        return False
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:4566/_localstack/health", timeout=2)
        return r.status == 200
    except Exception:
        return False


def _kafka_up() -> bool:
    if SERVERLESS:
        return False
    try:
        from kafka import KafkaProducer
        p = KafkaProducer(bootstrap_servers="localhost:9092", request_timeout_ms=2000)
        p.close(timeout=1)
        return True
    except Exception:
        return False


def _run_path(path_name: str, saga_id: str, use_cloud: bool):
    from saga_bench.config import FAILING_STEP, SERVICES, COMPENSATION_EDGES
    from saga_bench.fault_injector import FaultInjector
    from saga_bench.graph import default_graph, verify_rollback
    from saga_bench.services import build_services
    from saga_bench.event_log import EventLog
    from saga_bench.saga_store import SagaStore
    from saga_bench.lease_store import LeaseStore

    fault = FaultInjector(default_fail_step=FAILING_STEP)
    services = build_services()
    graph = default_graph()

    if use_cloud:
        from cloud.dynamo_event_log import DynamoEventLog
        from cloud.dynamo_saga_store import DynamoSagaStore
        from cloud.dynamo_lease_store import DynamoLeaseStore
        event_log = DynamoEventLog()
        saga_store = DynamoSagaStore()
        lease_store = DynamoLeaseStore()
    else:
        event_log = EventLog()
        saga_store = SagaStore()
        lease_store = LeaseStore()

    start_ms = time.perf_counter() * 1000

    if path_name == "path_a":
        from saga_bench.paths.orchestration import run_path_a
        result = run_path_a(saga_id, event_log, fault, services=services, saga_store=saga_store)
    elif path_name == "path_b":
        from saga_bench.paths.choreography import run_path_b
        result = run_path_b(saga_id, event_log, fault, services=services, saga_store=saga_store)
    elif path_name == "path_d":
        from saga_bench.paths.path_d import run_path_d
        result = run_path_d(saga_id, event_log, fault, services=services,
                           saga_store=saga_store, lease_store=lease_store, graph=graph)
    else:
        return {"error": f"Unknown path: {path_name}"}

    elapsed_ms = time.perf_counter() * 1000 - start_ms
    correct = verify_rollback(event_log, saga_id)

    rows = sorted(event_log.rows_for(saga_id), key=lambda r: r.timestamp_ms)
    base = rows[0].timestamp_ms if rows else 0
    timeline = []
    for r in rows:
        timeline.append({
            "t": round(r.timestamp_ms - base, 1),
            "event": r.event,
            "step": r.step or "",
        })

    dynamo_state = None
    if use_cloud:
        try:
            from cloud.config import get_client, SAGA_STATE_TABLE, EVENT_LOG_TABLE
            dynamodb = get_client("dynamodb")
            resp = dynamodb.get_item(TableName=SAGA_STATE_TABLE, Key={"saga_id": {"S": saga_id}})
            item = resp.get("Item", {})
            dynamo_state = {
                "completed": sorted(item.get("completed_steps", {}).get("SS", [])),
                "compensated": sorted(item.get("compensated_steps", {}).get("SS", [])),
                "event_count": dynamodb.query(
                    TableName=EVENT_LOG_TABLE,
                    KeyConditionExpression="saga_id = :sid",
                    ExpressionAttributeValues={":sid": {"S": saga_id}},
                    Select="COUNT",
                )["Count"],
            }
        except Exception:
            pass

    return {
        "saga_id": saga_id,
        "path": path_name,
        "completed": result.get("completed", []),
        "compensated": result.get("compensated", []),
        "correct": correct,
        "elapsed_ms": round(elapsed_ms, 1),
        "orchestrator": result.get("orchestrator", None),
        "timeline": timeline,
        "backend": "DynamoDB + LocalStack" if use_cloud else "In-Memory (Python)",
        "dynamo_state": dynamo_state,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", page="home")

@app.route("/demo")
def demo():
    return render_template("demo.html", page="demo")

@app.route("/results")
def results():
    return render_template("results.html", page="results")

@app.route("/architecture")
def architecture():
    return render_template("architecture.html", page="architecture")

@app.route("/about")
def about():
    return render_template("about.html", page="about")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/run/<path_name>")
def run_path(path_name):
    cloud = _use_cloud()
    saga_id = f"web-{path_name}-{int(time.time() * 1000)}"
    result = _run_path(path_name, saga_id, use_cloud=cloud)
    return jsonify(result)

@app.route("/api/run-all")
def run_all():
    cloud = _use_cloud()
    ts = int(time.time() * 1000)
    results = {}
    for p in ["path_a", "path_b", "path_d"]:
        saga_id = f"web-{p}-{ts}"
        results[p] = _run_path(p, saga_id, use_cloud=cloud)
    return jsonify(results)

@app.route("/api/status")
def status():
    return jsonify({
        "localstack": _use_cloud(),
        "kafka": _kafka_up(),
        "serverless": SERVERLESS,
    })

@app.route("/slides/<path:filename>")
def serve_slide(filename):
    return send_from_directory(str(SLIDES), filename)


if __name__ == "__main__":
    os.makedirs(PROJECT / "web" / "static", exist_ok=True)
    print()
    print("  Saga Compensation Benchmark")
    print("  http://localhost:5000")
    print()
    app.run(debug=False, port=5000)
