"""MongoDB-based job application tracker with user authentication."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from pymongo import MongoClient, DESCENDING

from config import MONGO_URI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MongoDB connection
# ---------------------------------------------------------------------------

_client: Optional[MongoClient] = None
_db = None


def _fix_mongo_uri(uri: str) -> str:
    """URL-encode username and password if they contain special characters."""
    if "://" not in uri:
        return uri
    # Split: mongodb+srv://user:pass@host/...
    scheme, rest = uri.split("://", 1)
    if "@" not in rest:
        return uri
    userinfo, hostpart = rest.rsplit("@", 1)
    if ":" in userinfo:
        user, passwd = userinfo.split(":", 1)
        user = quote_plus(user)
        passwd = quote_plus(passwd)
        userinfo = f"{user}:{passwd}"
    return f"{scheme}://{userinfo}@{hostpart}"


def _get_db():
    """Get (or lazily create) the MongoDB database connection."""
    global _client, _db
    if _db is not None:
        return _db

    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is not set. Add it to your .env file.")

    import certifi
    safe_uri = _fix_mongo_uri(MONGO_URI)
    _client = MongoClient(safe_uri, tlsCAFile=certifi.where())
    _db = _client.get_default_database(default="jobbot")
    logger.info(f"Connected to MongoDB: {_db.name}")
    return _db


def _id_str(doc: dict) -> dict:
    """Convert MongoDB _id (ObjectId) to string 'id' for JSON compatibility."""
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc


def _to_object_id(id_val):
    """Convert a string or int ID to ObjectId if possible."""
    if isinstance(id_val, ObjectId):
        return id_val
    try:
        return ObjectId(str(id_val))
    except Exception:
        return None


def init_db():
    """Ensure indexes exist on all collections."""
    db = _get_db()

    # Users indexes
    db.users.create_index("email", unique=True)

    # Jobs indexes
    db.jobs.create_index([("user_id", 1), ("url", 1)], unique=True)
    db.jobs.create_index([("score", DESCENDING)])
    db.jobs.create_index("status")
    db.jobs.create_index("source")
    db.jobs.create_index("user_id")

    # Search runs index
    db.search_runs.create_index("user_id")

    logger.info("MongoDB indexes ensured")


# ---------------------------------------------------------------------------
# Internal helper used by routes/auth.py  (replaces sqlite _get_conn)
# ---------------------------------------------------------------------------

def _get_conn():
    """Return the db handle — kept for compatibility with routes/auth.py."""
    return _get_db()


# ---------------------------------------------------------------------------
# User auth helpers
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password: str) -> Optional[dict]:
    """Create a new user. Returns user dict or None if email exists."""
    db = _get_db()
    doc = {
        "name": name,
        "email": email.lower().strip(),
        "password_hash": generate_password_hash(password),
        "profile": "{}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = db.users.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        del doc["_id"]
        del doc["password_hash"]
        return doc
    except Exception:
        return None


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Verify credentials. Returns user dict or None."""
    db = _get_db()
    row = db.users.find_one({"email": email.lower().strip()})
    if row and check_password_hash(row["password_hash"], password):
        return {
            "id": str(row["_id"]),
            "name": row["name"],
            "email": row["email"],
            "profile": row.get("profile", "{}"),
            "created_at": row.get("created_at", ""),
        }
    return None


def get_user_by_id(user_id) -> Optional[dict]:
    """Get user by ID (no password hash)."""
    db = _get_db()
    oid = _to_object_id(user_id)
    if not oid:
        return None
    row = db.users.find_one({"_id": oid})
    if not row:
        return None
    return {
        "id": str(row["_id"]),
        "name": row["name"],
        "email": row["email"],
        "profile": row.get("profile", "{}"),
        "created_at": row.get("created_at", ""),
    }


def update_user_profile(user_id, profile_data: dict):
    """Save profile JSON for a user. Auto-sets updated timestamp."""
    profile_data["profile_updated_at"] = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    oid = _to_object_id(user_id)
    if oid:
        db.users.update_one(
            {"_id": oid},
            {"$set": {"profile": json.dumps(profile_data)}},
        )


def get_not_interested_reasons(user_id) -> list[str]:
    """Return user's saved custom not-interested reasons."""
    db = _get_db()
    oid = _to_object_id(user_id)
    if not oid:
        return []
    row = db.users.find_one({"_id": oid}, {"not_interested_reasons": 1})
    if not row:
        return []
    return row.get("not_interested_reasons", [])


def save_not_interested_reason(user_id, reason: str) -> list[str]:
    """Add a custom not-interested reason for a user (deduped, max 20). Returns updated list."""
    reason = reason.strip()
    if not reason:
        return get_not_interested_reasons(user_id)
    db = _get_db()
    oid = _to_object_id(user_id)
    if not oid:
        return []
    # Pull current list, dedupe, cap at 20
    current = get_not_interested_reasons(user_id)
    if reason not in current:
        current = ([reason] + current)[:20]
        db.users.update_one({"_id": oid}, {"$set": {"not_interested_reasons": current}})
    return current


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def save_job(job, score_data: dict, cover_letter: str = "", user_id=None) -> bool:
    """Save a job to the database. Returns True if new, False if exists."""
    db = _get_db()
    doc = _build_job_doc(job, score_data, cover_letter, user_id)
    try:
        db.jobs.insert_one(doc)
        return True
    except Exception:
        return False


def _build_job_doc(job, score_data: dict, cover_letter: str = "", user_id=None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    # Keep only essential score fields to save DB space
    slim_score = {
        "local_score": score_data.get("local_score", 0),
        "final_score": score_data.get("final_score", 0),
    }
    return {
        "user_id": str(user_id) if user_id else None,
        "title": job.title[:200],
        "company": job.company[:100],
        "location": job.location[:100] if job.location else "",
        "url": job.url,
        "source": job.source,
        "description": (job.description or "")[:3000],
        "salary": (job.salary or "")[:50],
        "tags": json.dumps(job.tags[:10]) if isinstance(job.tags, list) else (job.tags or "[]"),
        "date_posted": job.date_posted,
        "job_type": job.job_type,
        "score": score_data.get("final_score", 0.0),
        "score_details": json.dumps(slim_score),
        "status": "new",
        "cover_letter": cover_letter,
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }


def save_jobs_bulk(ranked: list[tuple], user_id=None) -> int:
    """Save multiple jobs in one bulk operation. Returns count of new jobs inserted."""
    db = _get_db()
    docs = [_build_job_doc(job, score_data, user_id=user_id) for job, score_data in ranked]
    if not docs:
        return 0

    from pymongo import InsertOne
    from pymongo.errors import BulkWriteError

    ops = [InsertOne(doc) for doc in docs]
    try:
        result = db.jobs.bulk_write(ops, ordered=False)
        return result.inserted_count
    except BulkWriteError as e:
        # Some inserts fail due to duplicate (user_id, url) — that's expected
        return e.details.get("nInserted", 0)


def update_job_status(job_id, status: str, notes: str = ""):
    """Update job application status."""
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one(
            {"_id": oid},
            {"$set": {"status": status, "notes": notes,
                       "updated_at": datetime.now(timezone.utc).isoformat()}},
        )


VALID_SORT_FIELDS = {"score", "date_posted", "updated_at", "created_at", "title", "company", "salary"}


def get_jobs(
    status: Optional[str] = None,
    status_in: Optional[list] = None,
    status_nin: Optional[list] = None,
    min_score: float = 0.0,
    page: int = 1,
    per_page: int = 50,
    source: Optional[str] = None,
    sort_by: str = "score",
    sort_dir: str = "desc",
    search: Optional[str] = None,
    user_id=None,
) -> tuple[list[dict], int]:
    """Retrieve paginated jobs with optional filters, search, and sort."""
    from pymongo import ASCENDING
    db = _get_db()
    query: dict = {"score": {"$gte": min_score}}

    if user_id is not None:
        query["user_id"] = str(user_id)
    if status:
        query["status"] = status
    elif status_in:
        query["status"] = {"$in": status_in}
    elif status_nin:
        query["status"] = {"$nin": status_nin}
    if source:
        query["source"] = source

    # Full-text search across title, company, location
    if search and search.strip():
        pattern = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"title": pattern},
            {"company": pattern},
            {"location": pattern},
            {"tags": pattern},
        ]

    total = db.jobs.count_documents(query)
    skip = (page - 1) * per_page
    sort_field = sort_by if sort_by in VALID_SORT_FIELDS else "score"
    direction = ASCENDING if sort_dir == "asc" else DESCENDING
    cursor = db.jobs.find(query).sort(sort_field, direction).skip(skip).limit(per_page)
    return [_id_str(doc) for doc in cursor], total


def get_job_by_id(job_id, user_id=None) -> Optional[dict]:
    """Get a single job by ID, optionally scoped to a user."""
    db = _get_db()
    oid = _to_object_id(job_id)
    if not oid:
        return None

    query: dict = {"_id": oid}
    if user_id is not None:
        query["user_id"] = str(user_id)

    doc = db.jobs.find_one(query)
    return _id_str(doc) if doc else None


def get_stats(user_id=None) -> dict:
    """Get dashboard statistics, optionally scoped to a user."""
    db = _get_db()
    base_filter: dict = {}
    if user_id is not None:
        base_filter["user_id"] = str(user_id)

    # Status counts
    all_statuses = ["new", "saved", "applied", "interview", "offer", "rejected", "not_interested"]
    stats = {"total": db.jobs.count_documents(base_filter)}
    for s in all_statuses:
        stats[s] = db.jobs.count_documents({**base_filter, "status": s})

    # Average score
    pipeline = [{"$match": base_filter}, {"$group": {"_id": None, "avg": {"$avg": "$score"}}}]
    result = list(db.jobs.aggregate(pipeline))
    stats["avg_score"] = result[0]["avg"] if result and result[0]["avg"] else 0

    # Score distribution (buckets: 0-20, 20-40, 40-60, 60-80, 80-100)
    buckets = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
    score_dist = []
    for i in range(len(buckets) - 1):
        cnt = db.jobs.count_documents({**base_filter, "score": {"$gte": buckets[i], "$lt": buckets[i+1]}})
        score_dist.append({"label": f"{int(buckets[i]*100)}-{int(buckets[i+1]*100)}%", "count": cnt})
    stats["score_distribution"] = score_dist

    # Top companies by job count
    pipeline = [
        {"$match": base_filter},
        {"$group": {"_id": "$company", "count": {"$sum": 1}, "avg_score": {"$avg": "$score"}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    stats["top_companies"] = [
        {"name": r["_id"], "count": r["count"], "avg_score": round(r["avg_score"] * 100)}
        for r in db.jobs.aggregate(pipeline) if r["_id"]
    ]

    # Daily activity — jobs added per day for last 14 days
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    daily = {}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        daily[d] = 0
    pipeline = [
        {"$match": {**base_filter, "created_at": {"$gte": (today - timedelta(days=13)).isoformat()}}},
        {"$group": {"_id": {"$substr": ["$created_at", 0, 10]}, "count": {"$sum": 1}}},
    ]
    for r in db.jobs.aggregate(pipeline):
        if r["_id"] in daily:
            daily[r["_id"]] = r["count"]
    stats["daily_activity"] = [{"date": d, "count": c} for d, c in daily.items()]

    # Application funnel stages
    stats["funnel"] = [
        {"stage": "Discovered",    "count": stats["total"]},
        {"stage": "New",           "count": stats["new"] + stats.get("saved", 0)},
        {"stage": "Applied",       "count": stats["applied"] + stats["interview"] + stats.get("offer", 0)},
        {"stage": "Interview",     "count": stats["interview"] + stats.get("offer", 0)},
        {"stage": "Offer",         "count": stats.get("offer", 0)},
    ]

    return stats


def log_search_run(queries: list[str], total_found: int, total_matched: int,
                   sources: list[str], user_id=None):
    """Log a search run for analytics."""
    db = _get_db()
    db.search_runs.insert_one({
        "user_id": str(user_id) if user_id else None,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "total_found": total_found,
        "total_matched": total_matched,
        "sources": sources,
    })


# Initialize on import
init_db()
