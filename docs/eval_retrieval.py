import requests, psycopg2

DB = dict(host="localhost", port=5432, dbname="rolestream",
          user="rolestream", password="rolestream_dev")

# (question, SQL condition that defines the true postings)
CASES = [
    ("Are there any postings requiring Kubernetes?", "description ~* 'kubernetes'"),
    ("Which companies are hiring for Rust developers?", "description ~* '\\mrust\\M'"),
    ("Is there a posting that mentions React specifically?", "description ~ '\\mReact\\M'"),
    ("Is there a role that mentions Terraform?", "description ~* 'terraform'"),
    ("Is there a role mentioning GraphQL?", "description ~* 'graphql'"),
    ("Are there any postings requiring Docker?", "description ~* 'docker'"),
    ("Which roles mention Java experience?", "description ~ '\\mJava\\M'"),
    ("Which companies are hiring for PostgreSQL experience?", "description ~* 'postgres'"),
    ("Which companies are hiring for data engineer roles?", "title ~* 'data engineer'"),
    ("Which companies are hiring for security engineers?", "title ~* 'security'"),
    ("Which companies are hiring for solutions architects?", "title ~* 'solutions architect'"),
    ("Which roles mention Go experience?", "description ~ '\\m(Go|Golang)\\M' and description !~ 'Go-To-Market'"),
]

conn = psycopg2.connect(**DB)
cur = conn.cursor()

hits, precs = 0, []
for q, cond in CASES:
    cur.execute(f"select url from postings where status='open' and {cond}")
    truth = {r[0] for r in cur.fetchall()}
    sources = requests.post("http://localhost:8000/query",
                            json={"question": q}, timeout=300).json()["sources"]
    urls = [s["url"] for s in sources]
    good = sum(u in truth for u in urls)
    hit = good > 0
    hits += hit
    precs.append(good / max(len(urls), 1))
    print(f"{'HIT ' if hit else 'MISS'} {good}/{len(urls)}  truth={len(truth):4d}  {q}")

print(f"\nrecall@5 (any hit): {hits}/{len(CASES)}")
print(f"mean precision@5:   {sum(precs)/len(precs):.3f}")
