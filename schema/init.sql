-- RoleStream: postings table
-- Stores the normalized, current state of job postings pulled from
-- Greenhouse, Lever, and Ashby. Debezium watches this table for
-- inserts/updates/deletes and emits them as Kafka events.

CREATE TABLE IF NOT EXISTS postings (
    id              TEXT PRIMARY KEY,       -- hash of (source, source_id)
    source          TEXT NOT NULL,          -- 'greenhouse' | 'lever' | 'ashby'
    source_id       TEXT NOT NULL,          -- the ATS's own posting ID
    company         TEXT NOT NULL,
    title           TEXT NOT NULL,
    department      TEXT,
    location        TEXT,
    description     TEXT NOT NULL,
    salary_min      NUMERIC,
    salary_max      NUMERIC,
    employment_type TEXT,
    posted_at       TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'closed'
    url             TEXT,

    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_postings_source_sourceid
    ON postings (source, source_id);

CREATE INDEX IF NOT EXISTS idx_postings_updated_at
    ON postings (updated_at);

ALTER TABLE postings REPLICA IDENTITY FULL;
ALTER TABLE postings ADD COLUMN content_hash TEXT;
ALTER TABLE postings ADD COLUMN currency TEXT;