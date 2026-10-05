import json
import time
import requests

API_URL = "http://localhost:8000/query"
OUTPUT_FILE = "golden_results.json"
MAX_ATTEMPTS = 3

with open(OUTPUT_FILE) as f:
    results = json.load(f)

failed = [i for i, r in enumerate(results) if "error" in r["result"]]
print(f"{len(failed)} failed questions to retry")

for n, i in enumerate(failed, 1):
    question = results[i]["question"]
    print(f"[{n}/{len(failed)}] {question}")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.post(API_URL, json={"question": question}, timeout=300)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            results[i]["result"] = r.json()
            print("   ok")
            break
        except Exception as e:
            print(f"   attempt {attempt} failed: {str(e)[:200]}")
            results[i]["result"] = {"error": str(e)}
            time.sleep(5)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

errors = sum(1 for r in results if "error" in r["result"])
print(f"\nDone. {len(results) - errors}/{len(results)} succeeded")
