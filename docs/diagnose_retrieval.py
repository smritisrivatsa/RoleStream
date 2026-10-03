import requests

EMBED_URL = "http://localhost:8001/embed"
QDRANT_URL = "http://localhost:6333"
COLLECTION = "postings"

def embed(text):
    r = requests.post(EMBED_URL, json={"texts": [text]}, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["embeddings"][0], data["sparse_embeddings"][0]

def search_single(dense_vec, sparse_vec, mode, limit=10):
    if mode == "dense":
        body = {"query": dense_vec, "using": "dense", "limit": limit, "with_payload": True}
    else:
        body = {
            "query": {"indices": sparse_vec["indices"], "values": sparse_vec["values"]},
            "using": "sparse", "limit": limit, "with_payload": True,
        }
    r = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/query", json=body, timeout=30)
    r.raise_for_status()
    return r.json()["result"]["points"]

question = "Which companies are hiring for data engineer roles?"
dense_vec, sparse_vec = embed(question)

print("=== DENSE-ONLY results ===")
for h in search_single(dense_vec, sparse_vec, "dense"):
    print(f"  {h['score']:.3f} | {h['payload']['company']} | {h['payload']['title']}")

print("\n=== SPARSE-ONLY (BM25) results ===")
for h in search_single(dense_vec, sparse_vec, "sparse"):
    print(f"  {h['score']:.3f} | {h['payload']['company']} | {h['payload']['title']}")

print("\n=== RRF FUSION (matching production query) ===")
raw_limit = 15
body = {
    "prefetch": [
        {"query": dense_vec, "using": "dense", "limit": raw_limit},
        {"query": {"indices": sparse_vec["indices"], "values": sparse_vec["values"]}, "using": "sparse", "limit": raw_limit},
    ],
    "query": {"fusion": "rrf"},
    "limit": raw_limit,
    "with_payload": True,
}
r = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/query", json=body, timeout=30)
r.raise_for_status()
for h in r.json()["result"]["points"]:
    print(f"  {h['score']:.3f} | {h['payload']['company']} | {h['payload']['title']}")
