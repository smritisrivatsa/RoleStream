# pollers/greenhouse_poller.py

import requests
import hashlib
import html
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

# Companies to poll — board_token is the slug in their Greenhouse URL
COMPANIES = [
    "stripe", "airbnb", "pinterest", "robinhood", "coinbase",
    "databricks", "anthropic", "twitch", "figma", "brex",
    "asana", "gitlab", "cloudflare", "discord",
]

def make_id(source: str, source_id: str) -> str:
    """Generate a stable internal ID from source + source_id."""
    raw = f"{source}:{source_id}"
    return hashlib.sha256(raw.encode()).hexdigest()

def strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    unescaped = raw_html
    for _ in range(3):
        new_unescaped = html.unescape(unescaped)
        if new_unescaped == unescaped:
            break
        unescaped = new_unescaped
    return BeautifulSoup(unescaped, "html.parser").get_text(separator=" ", strip=True)

def fetch_greenhouse_jobs(board_token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    params = {"content": "true"}  # needed to get full description text
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("jobs", [])


def normalize_greenhouse_job(job: dict, company: str) -> dict:
    """Map a raw Greenhouse job into our internal postings schema."""
    departments = job.get("departments", [])
    department = departments[0]["name"] if departments else None

    return {
        "id": make_id("greenhouse", str(job["id"])),
        "source": "greenhouse",
        "source_id": str(job["id"]),
        "company": company,
        "title": job["title"],
        "department": department,
        "location": job.get("location", {}).get("name"),
        "description": strip_html(job.get("content", "")),
        "salary_min": None,
        "salary_max": None,
        "employment_type": None,
        "posted_at": job.get("first_published"),
        "updated_at": job["updated_at"],
        "status": "open",
        "url": job.get("absolute_url"),
    }


def upsert_posting(cursor, posting: dict):
    """Insert new posting, or update it if source_id already exists and changed."""
    cursor.execute(
        """
        INSERT INTO postings (
            id, source, source_id, company, title, department, location,
            description, salary_min, salary_max, employment_type,
            posted_at, updated_at, status, url
        )
        VALUES (
            %(id)s, %(source)s, %(source_id)s, %(company)s, %(title)s,
            %(department)s, %(location)s, %(description)s, %(salary_min)s,
            %(salary_max)s, %(employment_type)s, %(posted_at)s, %(updated_at)s,
            %(status)s, %(url)s
        )
        ON CONFLICT (source, source_id) DO UPDATE SET
            title = EXCLUDED.title,
            department = EXCLUDED.department,
            location = EXCLUDED.location,
            description = EXCLUDED.description,
            updated_at = EXCLUDED.updated_at,
            status = EXCLUDED.status,
            url = EXCLUDED.url
        WHERE postings.updated_at < EXCLUDED.updated_at;
        """,
        posting,
    )


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()

    for board_token in COMPANIES:
        print(f"Polling Greenhouse: {board_token}")
        jobs = fetch_greenhouse_jobs(board_token)
        for job in jobs:
            posting = normalize_greenhouse_job(job, company=board_token.capitalize())
            upsert_posting(cursor, posting)
        print(f"  -> processed {len(jobs)} postings")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run()