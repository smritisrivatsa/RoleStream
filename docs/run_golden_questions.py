import json
import requests

QUESTIONS = [
    "Which roles mention Go experience?",
    "Are there any postings requiring Kubernetes?",
    "Which companies are hiring for Rust developers?",
    "Is there a posting that mentions React specifically?",
    "Which roles require SQL experience?",
    "Which companies are hiring for data engineer roles?",
    "Compare backend engineering requirements at Stripe and ClickHouse",
    "Which companies have open roles in the AI/ML space?",
    "What's the salary range for engineering roles at OpenAI?",
    "Which companies pay over $200k for senior roles?",
    "Is there a 'Chief Vibes Officer' role posted anywhere?",
    "Are there any postings for COBOL developers?",
    "Which companies posted new roles in the last week?",
    "Has any Anthropic posting changed recently?",
    "What's the most recently posted role at Stripe?",
    "What departments at OpenAI currently have open roles?",
    "Is ClickHouse hiring in Singapore?",
    "What roles does Anthropic have open in San Francisco?",
    "Is Sarvam hiring for any engineering roles?",
    "What kind of roles does Modal have open?",
    "Which roles mention Python experience?",
    "Are there any postings requiring TypeScript?",
    "Is there a role that mentions Terraform?",
    "Which companies are hiring for PostgreSQL experience?",
    "Which companies are hiring for product management roles?",
    "Compare sales roles at Anthropic and Stripe",
    "Which companies have the most open engineering roles right now?",
    "Is there a role for a 'Senior Dinosaur Wrangler'?",
    "Are there any postings mentioning Fortran?",
    "Is there a marketing role that requires blockchain experience?",
    "What's the highest-paying engineering role you can find?",
    "Which companies offer salaries above $300k?",
    "What's the salary range for a Product Manager role at Ramp?",
    "What roles does Notion have open right now?",
    "Is Perplexity hiring for research positions?",
    "What departments does Linear have open roles in?",
    "Is Hightouch currently hiring?",
    "What's Robinhood's current open engineering headcount look like?",
    "Which companies are hiring for security engineers?",
    "Are there any DevOps roles open right now?",
    "Which companies have open roles for technical writers?",
    "Which companies are hiring for solutions architects?",
    "Which roles mention Java experience?",
    "Are there any postings requiring Docker?",
    "Is there a role mentioning GraphQL?",
    "Which companies want candidates with AWS experience?",
    "Which roles were posted today?",
    "Has the ClickHouse 'Senior Software Engineer - Postgres' role changed?",
    "Which companies have posted the most new roles this month?",
    "Is there a role requiring 20+ years of blockchain experience?",
    "Are there any postings for a 'Time Travel Consultant'?",
    "Is there an entry-level Chief Executive Officer role?",
    "What's the difference between the data engineer roles at two different companies?",
    "Which companies don't currently have any open roles?",
    "What's a role that requires both Python and Go?",
]

API_URL = "http://localhost:8000/query"
OUTPUT_FILE = "golden_results.json"


def run():
    results = []
    for i, question in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] {question}")
        try:
            r = requests.post(API_URL, json={"question": question}, timeout=300)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            data = {"error": str(e)}
        results.append({"question": question, "result": data})

        # Save incrementally so partial progress isn't lost if something crashes
        with open(OUTPUT_FILE, "w") as f:
            json.dump(results, f, indent=2)

    print(f"\nDone. Results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()