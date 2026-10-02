import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

EMBED_URL = "http://localhost:8001/embed"
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434/api/chat"
COLLECTION = "postings"
MODEL = "llama3.2:3b"

KNOWN_COMPANIES = [
    "Stripe", "Airbnb", "Pinterest", "Robinhood", "Coinbase", "Databricks",
    "Anthropic", "Twitch", "Figma", "Brex", "Asana", "Gitlab", "Cloudflare",
    "Discord", "Spotify", "Anchorage", "Ro", "Plaid", "Notion", "Ramp",
    "Linear", "Perplexity", "Vercel", "OpenAI", "Mercury", "Sarvam",
    "ClickHouse", "Modal", "Hex", "Hightouch",
]

def extract_company(question: str) -> str | None:
    """check if any known company name appears in the question, so we can
    auto-scope the search filter without the user needing to pass it explicitly."""
    question_lower = question.lower()
    for company in sorted(KNOWN_COMPANIES, key=len, reverse=True):
        if company.lower() in question_lower:
            return company
    return None

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


def embed(text: str) -> tuple[list[float], dict]:
    r = requests.post(EMBED_URL, json={"texts": [text]}, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["embeddings"][0], data["sparse_embeddings"][0]


def search(dense_vector: list[float], sparse_vector: dict, k: int, company: str | None) -> list[dict]:
    raw_limit = k * 3

    query_filter = None
    if company:
        query_filter = {"must": [{"key": "company", "match": {"value": company}}]}

    body = {
        "prefetch": [
            {
                "query": dense_vector,
                "using": "dense",
                "limit": raw_limit,
            },
            {
                "query": {
                    "indices": sparse_vector["indices"],
                    "values": sparse_vector["values"],
                },
                "using": "sparse",
                "limit": raw_limit,
            },
        ],
        "query": {"fusion": "rrf"},
        "limit": raw_limit,
        "with_payload": True,
    }
    if query_filter:
        body["filter"] = query_filter

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

    # Drop weak matches entirely rather than passing them to the LLM —
    # low RRF scores tend to be coincidental keyword overlaps (e.g. "Go"
    # matching "Go-To-Market") rather than genuinely relevant chunks.
    MIN_SCORE = 0.2
    filtered = [h for h in deduped if h["score"] >= MIN_SCORE]

    # Cap results per company so cross-company questions don't get
    # dominated by one company that happened to score well on everything.
    # Skipped entirely when a company filter is already applied, since
    # in that case every result is from the same company by design.
    if company is None:
        max_per_company = max(2, k // 2)
        company_counts = {}
        diverse = []
        for h in filtered:
            c = h["payload"].get("company")
            if company_counts.get(c, 0) < max_per_company:
                diverse.append(h)
                company_counts[c] = company_counts.get(c, 0) + 1
        filtered = diverse

    return filtered[:k]


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
        company = q.company or extract_company(q.question)
        dense_vec, sparse_vec = embed(q.question)
        hits = search(dense_vec, sparse_vec, q.top_k, company)
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
            "text": h["payload"].get("text"),
            "score": round(h["score"], 3),
        }
        for i, h in enumerate(hits, 1)
    ]
    return {"answer": answer, "sources": sources}