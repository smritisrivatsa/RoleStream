import psycopg2
from collections import Counter

conn = psycopg2.connect(
    host="localhost", port=5432, dbname="rolestream",
    user="rolestream", password="rolestream_dev"  # match your actual password
)
cur = conn.cursor()

cur.execute("SELECT DISTINCT company FROM postings")
companies = [r[0] for r in cur.fetchall()]

for company in companies:
    cur.execute("SELECT description FROM postings WHERE company = %s", (company,))
    descriptions = [r[0] for r in cur.fetchall()]
    if len(descriptions) < 3:
        continue

    # Split each description into sentences, count how often each sentence
    # appears verbatim across this company's postings
    sentence_counts = Counter()
    for desc in descriptions:
        sentences = [s.strip() for s in desc.split('.') if len(s.strip()) > 40]
        for s in set(sentences):  # count each sentence once per posting
            sentence_counts[s] += 1

    total = len(descriptions)
    boilerplate = [s for s, count in sentence_counts.items() if count / total >= 0.5]

    if boilerplate:
        print(f"\n=== {company} ({total} postings) ===")
        for b in boilerplate[:3]:
            pct = sentence_counts[b] / total * 100
            print(f"  [{pct:.0f}%] {b[:150]}...")
