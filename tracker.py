"""SQLite-based job application tracker with user authentication."""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from werkzeug.security import generate_password_hash, check_password_hash

from config import DB_PATH

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            profile TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT DEFAULT 'Remote',
            url TEXT NOT NULL,
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
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, url)
        );

        CREATE TABLE IF NOT EXISTS search_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            run_at TEXT DEFAULT (datetime('now')),
            queries TEXT,
            total_found INTEGER DEFAULT 0,
            total_matched INTEGER DEFAULT 0,
            sources TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
        CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """)
    conn.commit()

    # Migrate existing tables — add user_id column if missing
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN user_id INTEGER")
            logger.info("Migrated jobs table: added user_id column")

        # Drop the old UNIQUE(url) constraint by allowing duplicates per user
        # (new table already has UNIQUE(user_id, url) — old rows keep working)
    except Exception as e:
        logger.debug(f"Migration check: {e}")

    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(search_runs)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE search_runs ADD COLUMN user_id INTEGER")
            logger.info("Migrated search_runs table: added user_id column")
    except Exception as e:
        logger.debug(f"Migration check: {e}")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# User auth helpers
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password: str) -> Optional[dict]:
    """Create a new user. Returns user dict or None if email exists."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email.lower().strip(), generate_password_hash(password)),
        )
        conn.commit()
        user = conn.execute(
            "SELECT id, name, email, profile, created_at FROM users WHERE email = ?",
            (email.lower().strip(),)
        ).fetchone()
        return dict(user) if user else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns user dict or None."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return {"id": row["id"], "name": row["name"], "email": row["email"],
                "profile": row["profile"], "created_at": row["created_at"]}
    return None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID (no password hash)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, email, profile, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_profile(user_id: int, profile_data: dict):
    """Save profile JSON for a user."""
    conn = _get_conn()
    conn.execute(
        "UPDATE users SET profile = ? WHERE id = ?",
        (json.dumps(profile_data), user_id),
    )
    conn.commit()
    conn.close()


def save_job(job, score_data: dict, cover_letter: str = "", user_id: int = None) -> bool:
    """Save a job to the database. Returns True if new, False if exists."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO jobs
               (user_id, title, company, location, url, source, description, salary,
                tags, date_posted, job_type, score, score_details, cover_letter)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
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
    user_id: int = None,
) -> list[dict]:
    """Retrieve jobs with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM jobs WHERE score >= ?"
    params: list = [min_score]

    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
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


def get_job_by_id(job_id: int, user_id: int = None) -> Optional[dict]:
    """Get a single job by ID, optionally scoped to a user."""
    conn = _get_conn()
    if user_id is not None:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats(user_id: int = None) -> dict:
    """Get dashboard statistics, optionally scoped to a user."""
    conn = _get_conn()
    stats = {}

    where = "WHERE user_id = ?" if user_id is not None else ""
    p = (user_id,) if user_id is not None else ()

    stats["total"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", p).fetchone()[0]
    stats["new"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}{' AND' if where else 'WHERE'} status='new'", p).fetchone()[0]
    stats["applied"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}{' AND' if where else 'WHERE'} status='applied'", p).fetchone()[0]
    stats["interview"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}{' AND' if where else 'WHERE'} status='interview'", p).fetchone()[0]
    stats["rejected"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}{' AND' if where else 'WHERE'} status='rejected'", p).fetchone()[0]
    stats["saved"] = conn.execute(f"SELECT COUNT(*) FROM jobs {where}{' AND' if where else 'WHERE'} status='saved'", p).fetchone()[0]
    stats["avg_score"] = conn.execute(f"SELECT COALESCE(AVG(score), 0) FROM jobs {where}", p).fetchone()[0]

    sources = conn.execute(
        f"SELECT source, COUNT(*) as cnt FROM jobs {where} GROUP BY source ORDER BY cnt DESC", p
    ).fetchall()
    stats["by_source"] = {row["source"]: row["cnt"] for row in sources}

    stats["top_companies"] = [
        row["company"]
        for row in conn.execute(
            f"SELECT company, MAX(score) as s FROM jobs {where} GROUP BY company ORDER BY s DESC LIMIT 10", p
        ).fetchall()
    ]

    conn.close()
    return stats


def log_search_run(queries: list[str], total_found: int, total_matched: int,
                   sources: list[str], user_id: int = None):
    """Log a search run for analytics."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO search_runs (user_id, queries, total_found, total_matched, sources) VALUES (?, ?, ?, ?, ?)",
        (user_id, json.dumps(queries), total_found, total_matched, json.dumps(sources)),
    )
    conn.commit()
    conn.close()


# Initialize on import
init_db()
