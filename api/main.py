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
    "chunks provided. Cite the chunks you use like [1] or [2]. If the context "
    "does not contain the answer, say you could not find it in the postings. "
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
    body = {"query": vector, "limit": k, "with_payload": True}
    if company:
        body["filter"] = {"must": [{"key": "company", "match": {"value": company}}]}
    r = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/query", json=body, timeout=30
    )
    r.raise_for_status()
    return r.json()["result"]["points"]


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
            "company": h["payload"]["company"],
            "title": h["payload"]["title"],
            "url": h["payload"]["url"],
            "section": h["payload"]["section"],
            "score": round(h["score"], 3),
        }
        for i, h in enumerate(hits, 1)
    ]
    return {"answer": answer, "sources": sources}
