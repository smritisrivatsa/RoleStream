import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

EMBED_URL = "http://localhost:8001/embed"
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434/api/chat"
COLLECTION = "postings"
MODEL = "llama3.2:3b"

SYSTEM = (
    "You answer questions about job postings using ONLY the numbered context "
    "chunks provided. Always respond in at least one complete sentence. "
    "Cite the chunks you use with their number in brackets, like [1], placed "
    "after the relevant claim — never respond with only a citation number. "
    "If the context does not contain the answer, say so in a full sentence. "
    "Do not invent details."
)

app = FastAPI(title="RoleStream")


class Query(BaseModel):
    question: str
    top_k: int = 5
    company: str | None = None


def embed(text: str) -> list[float]:
    r = requests.post(EMBED_URL, json={"texts": [text]}, timeout=60)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def search(vector: list[float], k: int, company: str | None) -> list[dict]:
    # Retrieve more than k so we have room to dedupe by posting
    raw_limit = k * 3
    body = {"query": vector, "limit": raw_limit, "with_payload": True}
    if company:
        body["filter"] = {"must": [{"key": "company", "match": {"value": company}}]}
    r = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/query", json=body, timeout=30
    )
    r.raise_for_status()
    hits = r.json()["result"]["points"]

    # Keep only the best-scoring chunk per posting_id
    seen = {}
    for h in hits:
        pid = h["payload"]["posting_id"]
        if pid not in seen or h["score"] > seen[pid]["score"]:
            seen[pid] = h

    deduped = sorted(seen.values(), key=lambda h: h["score"], reverse=True)
    return deduped[:k]


def generate(question: str, hits: list[dict]) -> str:
    context = "\n\n".join(
        f"[{i}] {h['payload']['text']}" for i, h in enumerate(hits, 1)
    )
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        },
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


@app.post("/query")
def query(q: Query):
    try:
        hits = search(embed(q.question), q.top_k, q.company)
        if not hits:
            return {"answer": "No matching postings found.", "sources": []}
        answer = generate(q.question, hits)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))
    sources = [
        {
            "ref": i,
            "company": h["payload"].get("company"),
            "title": h["payload"].get("title"),
            "url": h["payload"].get("url"),
            "section": h["payload"].get("section"),
            "score": round(h["score"], 3),
        }
        for i, h in enumerate(hits, 1)
    ]
    return {"answer": answer, "sources": sources}