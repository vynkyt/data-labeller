import sys
import os
import libsql
import pytest

os.environ.setdefault("TURSO_DATABASE_URL", "libsql://test")
os.environ.setdefault("TURSO_AUTH_TOKEN", "fake")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SCHEMA = """
CREATE TABLE IF NOT EXISTS Job (
    job_id TEXT PRIMARY KEY,
    task_id TEXT
);
CREATE TABLE IF NOT EXISTS Task (
    task_id TEXT PRIMARY KEY,
    url TEXT,
    client_id TEXT,
    job_id TEXT,
    labeller_id TEXT,
    label TEXT,
    categories TEXT,
    status TEXT,
    qc_label TEXT,
    locked_at TEXT,
    ai_qc_status TEXT DEFAULT NULL,
    qc_round INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS AI (
    job_id TEXT PRIMARY KEY,
    total_tasks INTEGER,
    ai_processed INTEGER DEFAULT 0,
    bad_labellers TEXT
);
"""

@pytest.fixture
def db():
    conn = libsql.connect(":memory:")
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    return conn
