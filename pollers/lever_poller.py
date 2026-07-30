# pollers/lever_poller.py

import re
import requests
import hashlib
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

COMPANIES = [
    "leverdemo",
    # add more Lever company slugs here
]


def make_id(source: str, source_id: str) -> str:
    raw = f"{source}:{source_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)


def parse_salary_range(salary_text):
    if not salary_text:
        return None, None
    numbers = re.findall(r"\d[\d,]*", salary_text)
    numbers = [float(n.replace(",", "")) for n in numbers if n]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    elif len(numbers) == 1:
        return numbers[0], numbers[0]
    return None, None


def fetch_lever_jobs(company_slug: str) -> list:
    url = f"https://api.lever.co/v0/postings/{company_slug}"
    params = {"mode": "json"}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def normalize_lever_job(job: dict, company: str) -> dict:
    post_date_ms = job.get("createdAt") or job.get("post_date")
    posted_at = (
        datetime.fromtimestamp(post_date_ms / 1000, tz=timezone.utc)
        if post_date_ms else None
    )
    updated_at = posted_at  # see note below

    categories = job.get("categories", {})
    salary_text = categories.get("compensation")
    salary_min, salary_max = parse_salary_range(salary_text)

    raw_description = job.get("descriptionPlain") or job.get("description") or ""

    return {
        "id": make_id("lever", str(job["id"])),
        "source": "lever",
        "source_id": str(job["id"]),
        "company": company,
        "title": job.get("text", ""),
        "department": categories.get("team") or categories.get("department"),
        "location": categories.get("location"),
        "description": strip_html(raw_description),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "employment_type": categories.get("commitment"),
        "posted_at": posted_at,
        "updated_at": updated_at,
        "status": "open",
        "url": job.get("hostedUrl") or job.get("applyUrl"),
    }


def upsert_posting(cursor, posting: dict):
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
            salary_min = EXCLUDED.salary_min,
            salary_max = EXCLUDED.salary_max,
            employment_type = EXCLUDED.employment_type,
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

    for company_slug in COMPANIES:
        print(f"Polling Lever: {company_slug}")
        jobs = fetch_lever_jobs(company_slug)
        for job in jobs:
            posting = normalize_lever_job(job, company=company_slug.capitalize())
            upsert_posting(cursor, posting)
        print(f"  -> processed {len(jobs)} postings")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run()