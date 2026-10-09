"""Sequential load test: sends N queries to /query, prints client-side latency.
Ollama serves one generation at a time on this machine, so concurrency mostly
queues requests; run this at concurrency 1 for clean per-stage numbers."""
import statistics
import sys
import time

import requests

URL = "http://localhost:8000/query"
QUESTIONS = [
    "Which roles mention Kubernetes?",
    "data engineer roles",
    "Which companies are hiring for Python and Golang?",
    "Compare backend roles at Stripe and ClickHouse",
    "What does Anthropic look for in research engineers?",
    "Which roles mention Rust?",
    "Any machine learning engineer roles at Databricks?",
    "Which roles require experience with Kafka?",
    "What salary ranges are listed for Coinbase roles?",
    "Which roles mention Terraform?",
]

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30

# Warm-up so model load time doesn't count.
requests.post(URL, json={"question": QUESTIONS[0]}, timeout=300)

times, errors = [], 0
for i in range(n):
    q = QUESTIONS[i % len(QUESTIONS)]
    t = time.perf_counter()
    try:
        r = requests.post(URL, json={"question": q}, timeout=300)
        r.raise_for_status()
        times.append(time.perf_counter() - t)
    except requests.RequestException as e:
        errors += 1
        print(f"error on '{q}': {e}")
    print(f"{i + 1}/{n} {time.perf_counter() - t:.1f}s", end="\r")

times.sort()
print()
print(f"requests: {len(times)} ok, {errors} errors")
if times:
    print(f"p50: {statistics.median(times):.1f}s")
    print(f"p95: {times[int(0.95 * (len(times) - 1))]:.1f}s")
    print(f"max: {times[-1]:.1f}s")
