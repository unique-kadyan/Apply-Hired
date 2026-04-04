"""SQLite-based job application tracker."""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from config import DB_PATH

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT 'Remote',
            url TEXT UNIQUE NOT NULL,
            source TEXT,
            description TEXT,
            salary TEXT,
            tags TEXT DEFAULT '[]',
            date_posted TEXT,
            job_type TEXT DEFAULT 'remote',
            score REAL DEFAULT 0.0,
            score_details TEXT DEFAULT '{}',
            status TEXT DEFAULT 'new',
            cover_letter TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS search_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT DEFAULT (datetime('now')),
            queries TEXT,
            total_found INTEGER DEFAULT 0,
            total_matched INTEGER DEFAULT 0,
            sources TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
    """)
    conn.commit()
    conn.close()


def save_job(job, score_data: dict, cover_letter: str = "") -> bool:
    """Save a job to the database. Returns True if new, False if exists."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO jobs
               (title, company, location, url, source, description, salary,
                tags, date_posted, job_type, score, score_details, cover_letter)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.title,
                job.company,
                job.location,
                job.url,
                job.source,
                job.description,
                job.salary,
                json.dumps(job.tags),
                job.date_posted,
                job.job_type,
                score_data.get("final_score", 0.0),
                json.dumps(score_data),
                cover_letter,
            ),
        )
        conn.commit()
        return conn.total_changes > 0
    except sqlite3.Error as e:
        logger.error(f"DB save error: {e}")
        return False
    finally:
        conn.close()


def update_job_status(job_id: int, status: str, notes: str = ""):
    """Update job application status."""
    conn = _get_conn()
    conn.execute(
        "UPDATE jobs SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
        (status, notes, datetime.now(timezone.utc).isoformat(), job_id),
    )
    conn.commit()
    conn.close()


def get_jobs(
    status: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = 50,
    source: Optional[str] = None,
) -> list[dict]:
    """Retrieve jobs with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM jobs WHERE score >= ?"
    params: list = [min_score]

    if status:
        query += " AND status = ?"
        params.append(status)
    if source:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY score DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_job_by_id(job_id: int) -> Optional[dict]:
    """Get a single job by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats() -> dict:
    """Get dashboard statistics."""
    conn = _get_conn()
    stats = {}

    stats["total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    stats["new"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='new'").fetchone()[0]
    stats["applied"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied'").fetchone()[0]
    stats["interview"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='interview'").fetchone()[0]
    stats["rejected"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='rejected'").fetchone()[0]
    stats["saved"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='saved'").fetchone()[0]
    stats["avg_score"] = conn.execute("SELECT COALESCE(AVG(score), 0) FROM jobs").fetchone()[0]

    sources = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    stats["by_source"] = {row["source"]: row["cnt"] for row in sources}

    stats["top_companies"] = [
        row["company"]
        for row in conn.execute(
            "SELECT company, MAX(score) as s FROM jobs GROUP BY company ORDER BY s DESC LIMIT 10"
        ).fetchall()
    ]

    conn.close()
    return stats


def log_search_run(queries: list[str], total_found: int, total_matched: int, sources: list[str]):
    """Log a search run for analytics."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO search_runs (queries, total_found, total_matched, sources) VALUES (?, ?, ?, ?)",
        (json.dumps(queries), total_found, total_matched, json.dumps(sources)),
    )
    conn.commit()
    conn.close()


# Initialize on import
init_db()
