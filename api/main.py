import math
import re
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


def extract_companies(question: str) -> list[str]:
    """Return every known company named in the question, in the order they
    appear. Uses word boundaries so 'Ro' doesn't match inside 'roles'."""
    found = []
    for company in KNOWN_COMPANIES:
        m = re.search(r'\b' + re.escape(company) + r'\b', question, re.IGNORECASE)
        if m:
            found.append((m.start(), company))
    found.sort()
    return [c for _, c in found]


SYSTEM = (
    "You answer questions about job postings using ONLY the numbered context "
    "chunks provided. Always respond in at least one complete sentence. "
    "Cite the chunks you use with their number in brackets, like [1], placed "
    "after the relevant claim. "
    "If the context does not contain the answer, say so in a full sentence. "
    "Do not invent details.\n\n"
    "Specific rules:\n"
    "- Every chunk begins with the company and job title. When you cite a "
    "chunk, also name its company and job title, like 'Databricks - Sr. "
    "Solutions Architect [1]'. Never answer with only citation numbers.\n"
    "- Attribute a fact only to the company named at the start of the chunk "
    "it came from. Never credit one company's posting details to another.\n"
    "- Only state a number (salary, years of experience, etc.) if it appears "
    "exactly as written in a single chunk. Never combine, average, or infer "
    "a number from multiple chunks.\n"
    "- If asked whether something is absent or does not exist (e.g. 'which "
    "companies don't have X'), say that you can only confirm what exists in "
    "the provided postings, not confirm something is truly absent, since you "
    "only see a retrieved sample, not the full dataset.\n"
    "- The context contains NO posting dates or timestamps. For any question "
    "about when a role was posted, what is new, 'today', 'this week', "
    "'recently', or whether a posting has changed, say that posting dates "
    "are not available in the data. Never guess."
)

FILLER_WORDS = {
    "which", "what", "whats", "who", "where", "when", "how", "is", "are", "was",
    "were", "do", "does", "did", "there", "any", "a", "an", "the", "of", "for",
    "to", "in", "at", "on", "by", "with", "and", "or", "me", "you", "can",
    "companies", "company", "hiring", "hire", "hires", "roles", "role", "jobs",
    "job", "postings", "posting", "posted", "positions", "position", "open",
    "openings", "opening", "currently", "right", "now", "mention", "mentions",
    "mentioning", "require", "requires", "requiring", "required", "want",
    "wants", "experience", "find", "show", "list", "tell", "give", "s", "compare",
}

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


def rewrite_query(question: str) -> str:
    """Drop question framing and generic job-posting words, keep the topic
    words. Deterministic and cannot invent terms. If only one very short
    word survives (e.g. 'Go'), it is too ambiguous to embed alone, so fall
    back to the original question."""
    words = re.findall(r"[A-Za-z0-9+#./-]+", question)
    kept = [w for w in words if w.lower().strip(".") not in FILLER_WORDS]
    if not kept:
        return question
    if len(kept) == 1 and len(kept[0]) <= 3:
        return question
    return " ".join(kept)


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

    # Drop exact-duplicate chunks (same role posted several times).
    seen_text = set()
    unique = []
    for h in deduped:
        key = h["payload"].get("text")
        if key in seen_text:
            continue
        seen_text.add(key)
        unique.append(h)

    # Drop weak matches entirely rather than passing them to the LLM.
    MIN_SCORE = 0.2
    filtered = [h for h in unique if h["score"] >= MIN_SCORE]

    # Cap results per company so generic questions don't get dominated by
    # one company. Skipped when a company filter is applied.
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


def retrieve(dense_vec: list[float], sparse_vec: dict, k: int, companies: list[str]) -> list[dict]:
    """No company named: one open search. One company: search scoped to it.
    Two or more (a comparison): one scoped search per company, grouped in the
    order the companies were mentioned, so each side gets fair representation."""
    if len(companies) >= 2:
        per_company_k = max(2, math.ceil(k / len(companies)))
        hits = []
        for c in companies:
            hits.extend(search(dense_vec, sparse_vec, per_company_k, c))
        return hits
    return search(dense_vec, sparse_vec, k, companies[0] if companies else None)


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
        companies = [q.company] if q.company else extract_companies(q.question)
        dense_vec, sparse_vec = embed(rewrite_query(q.question))
        hits = retrieve(dense_vec, sparse_vec, q.top_k, companies)
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