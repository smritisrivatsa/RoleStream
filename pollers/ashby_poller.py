# pollers/ashby_poller.py

import hashlib
import requests
import psycopg2
from bs4 import BeautifulSoup
from datetime import datetime, timezone

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "rolestream",
    "user": "rolestream",
    "password": "rolestream_dev",
}

# Companies to poll — the slug in their Ashby job board URL
# (jobs.ashbyhq.com/{slug})
COMPANIES = [
    "notion", "ramp", "linear", "perplexity", "vercel",
    "openai", "mercury", "sarvam", "clickhouse", "modal",
    "hex", "hightouch"
]


def make_id(source: str, source_id: str) -> str:
    raw = f"{source}:{source_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def strip_html(raw_html: str) -> str:
    """Ashby's descriptionHtml is genuine, single-encoded HTML."""
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)


def extract_salary(job: dict) -> tuple:
    comp = job.get("compensation") or {}
    summary = comp.get("summaryComponents") or []
    for component in summary:
        if component.get("compensationType") == "Salary":
            min_val = component.get("minValue")
            max_val = component.get("maxValue")
            interval = component.get("interval", "")
            currency = component.get("currencyCode", "USD")

            if "HOUR" in interval.upper():
                if min_val is not None:
                    min_val = min_val * 2080
                if max_val is not None:
                    max_val = max_val * 2080

            return min_val, max_val, currency
    return None, None, None


def compute_content_hash(posting: dict) -> str:
    """Ashby doesn't expose a reliable 'last updated' field, so we hash
    the content ourselves to detect real changes between polls."""
    fields = "|".join([
        str(posting["title"]),
        str(posting["description"]),
        str(posting["location"]),
        str(posting["salary_min"]),
        str(posting["salary_max"]),
        str(posting["department"]),
    ])
    return hashlib.sha256(fields.encode()).hexdigest()


def fetch_ashby_jobs(company_slug: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    params = {"includeCompensation": "true"}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("jobs", [])


def normalize_ashby_job(job: dict, company: str) -> dict:
    salary_min, salary_max, currency = extract_salary(job)

    posted_at = None
    published_at = job.get("publishedAt")
    if published_at:
        posted_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

    posting = {
        "id": make_id("ashby", str(job["id"])),
        "source": "ashby",
        "source_id": str(job["id"]),
        "company": company,
        "title": job.get("title", ""),
        "department": job.get("department"),
        "location": job.get("location"),
        "description": strip_html(job.get("descriptionHtml", "")),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "currency": currency,
        "employment_type": job.get("employmentType"),
        "posted_at": posted_at,
        "status": "open",
        "url": job.get("jobUrl") or job.get("applyUrl"),
    }
    posting["content_hash"] = compute_content_hash(posting)
    return posting


def upsert_posting(cursor, posting: dict):
    """Ashby has no reliable updated_at, so we compare content_hash instead
    and set updated_at to NOW() ourselves whenever content actually changes."""
    cursor.execute(
        """
        INSERT INTO postings (
            id, source, source_id, company, title, department, location,
            description, salary_min, salary_max, currency, employment_type,
            posted_at, updated_at, status, url, content_hash
        )
        VALUES (
            %(id)s, %(source)s, %(source_id)s, %(company)s, %(title)s,
            %(department)s, %(location)s, %(description)s, %(salary_min)s,
            %(salary_max)s, %(currency)s, %(employment_type)s, %(posted_at)s, NOW(),
            %(status)s, %(url)s, %(content_hash)s
        )
        ON CONFLICT (source, source_id) DO UPDATE SET
            title = EXCLUDED.title,
            department = EXCLUDED.department,
            location = EXCLUDED.location,
            description = EXCLUDED.description,
            salary_min = EXCLUDED.salary_min,
            salary_max = EXCLUDED.salary_max,
            currency = EXCLUDED.currency,
            employment_type = EXCLUDED.employment_type,
            updated_at = NOW(),
            status = EXCLUDED.status,
            url = EXCLUDED.url,
            content_hash = EXCLUDED.content_hash
        WHERE postings.content_hash IS DISTINCT FROM EXCLUDED.content_hash;
        """,
        posting,
    )

def run():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()

    for company_slug in COMPANIES:
        print(f"Polling Ashby: {company_slug}")
        jobs = fetch_ashby_jobs(company_slug)
        for job in jobs:
            posting = normalize_ashby_job(job, company=company_slug)
            upsert_posting(cursor, posting)
        print(f"  -> processed {len(jobs)} postings")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run()