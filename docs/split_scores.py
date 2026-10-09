import json, math

# Questions where the right answer is "not in the data" or "no dates available".
# Verify each against Postgres before trusting this list.
NO_ANSWER = {
    "Is there a 'Chief Vibes Officer' role posted anywhere?",
    "Are there any postings for COBOL developers?",
    "Is there a role for a 'Senior Dinosaur Wrangler'?",
    "Are there any postings mentioning Fortran?",
    "Is there a role requiring 20+ years of blockchain experience?",
    "Are there any postings for a 'Time Travel Consultant'?",
    "Is there an entry-level Chief Executive Officer role?",
}
NO_DATES = {
    "Which companies posted new roles in the last week?",
    "Has any Anthropic posting changed recently?",
    "What's the most recently posted role at Stripe?",
    "Which roles were posted today?",
    "Has the ClickHouse 'Senior Software Engineer - Postgres' role changed?",
    "Which companies have posted the most new roles this month?",
}
REFUSAL_PHRASES = ["no ", "not ", "couldn't", "cannot", "can only confirm",
                   "don't", "doesn't", "unavailable", "not available"]

scores = json.load(open("ragas_scores.json"))
golden = {r["question"]: r["result"].get("answer", "") for r in json.load(open("golden_results.json"))}

def mean(rows, m):
    v = [r[m] for r in rows if r.get(m) is not None and not math.isnan(r[m])]
    return (sum(v) / len(v), len(v)) if v else (float("nan"), 0)

skip = NO_ANSWER | NO_DATES
answerable = [r for r in scores if r["user_input"] not in skip]
for m in ["faithfulness", "answer_relevancy"]:
    all_, n_all = mean(scores, m)
    ans, n_ans = mean(answerable, m)
    print(f"{m}: all={all_:.3f} (n={n_all})  answerable only={ans:.3f} (n={n_ans})")

def refused(a):
    a = a.lower()
    return any(p in a for p in REFUSAL_PHRASES)

for name, qs in [("no-answer", NO_ANSWER), ("no-dates", NO_DATES)]:
    ok = [q for q in qs if refused(golden.get(q, ""))]
    print(f"{name} refusal rate: {len(ok)}/{len(qs)}")
    for q in qs:
        if q not in ok:
            print("  MISSED:", q, "->", golden.get(q, "")[:120])