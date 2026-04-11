"""MongoDB-based job application tracker with user authentication."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

from bson import ObjectId
from pymongo import DESCENDING, MongoClient
from werkzeug.security import check_password_hash, generate_password_hash

from config import MONGO_URI

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_db = None

def _fix_mongo_uri(uri: str) -> str:
    """URL-encode username and password if they contain special characters."""
    if "://" not in uri:
        return uri
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

    db.users.create_index("email", unique=True)

    db.jobs.create_index([("user_id", 1), ("url", 1)], unique=True)
    db.jobs.create_index([("score", DESCENDING)])
    db.jobs.create_index("status")
    db.jobs.create_index("source")
    db.jobs.create_index("user_id")

    db.search_runs.create_index("user_id")

    logger.info("MongoDB indexes ensured")

def _get_conn():
    """Return the db handle — kept for compatibility with routes/auth.py."""
    return _get_db()

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
    current = get_not_interested_reasons(user_id)
    if reason not in current:
        current = ([reason] + current)[:20]
        db.users.update_one({"_id": oid}, {"$set": {"not_interested_reasons": current}})
    return current

def delete_not_interested_reason(user_id, reason: str) -> list[str]:
    """Remove a specific not-interested reason. Returns updated list."""
    db = _get_db()
    oid = _to_object_id(user_id)
    if not oid:
        return []
    current = get_not_interested_reasons(user_id)
    updated = [r for r in current if r != reason]
    db.users.update_one({"_id": oid}, {"$set": {"not_interested_reasons": updated}})
    return updated

_PREDEFINED_REASONS = frozenset(
    {
        "Salary too low",
        "Location not suitable",
        "Role mismatch — not what I do",
        "Company concerns",
        "Too senior / too junior",
        "Already applied elsewhere",
        "Poor job description",
        "Contract / freelance only",
    }
)

_SKIP_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        "too",
        "very",
        "just",
        "only",
        "also",
        "but",
        "and",
        "or",
        "not",
        "no",
        "nor",
        "so",
        "yet",
        "for",
        "in",
        "on",
        "at",
        "to",
        "of",
        "with",
        "by",
        "from",
        "as",
        "into",
        "this",
        "that",
        "these",
        "those",
        "what",
        "who",
        "when",
        "where",
        "how",
        "why",
        "all",
        "any",
        "each",
        "some",
        "such",
        "than",
        "i",
        "me",
        "my",
        "we",
        "us",
        "our",
        "they",
        "their",
        "role",
        "job",
        "position",
        "work",
        "company",
        "require",
        "requires",
        "required",
        "want",
        "looking",
        "dont",
        "already",
        "poor",
        "mismatch",
        "concerns",
        "issues",
        "type",
        "kind",
        "applied",
        "elsewhere",
        "description",
        "suitable",
        "using",
        "about",
        "because",
        "since",
        "while",
        "during",
        "which",
        "there",
        "here",
        "like",
        "more",
        "less",
        "other",
        "another",
        "same",
        "different",
        "good",
        "bad",
    }
)

def get_skip_filter_keywords(user_id) -> list[str]:
    """
    Derive keyword filters from the user's custom not-interested reasons.
    NOTE: These keywords are for display/tracking only and are NOT used to filter jobs during search.

    Only uses custom (non-predefined) reasons — generic reasons like
    "Salary too low" don't give actionable title-matching keywords.

    Returns a sorted list of lowercase keyword strings extracted from
    the user's custom not-interested reasons.
    """
    import re as _re

    db = _get_db()
    oid = _to_object_id(user_id)
    if not oid:
        return []

    custom_texts: list[str] = []

    user = db.users.find_one({"_id": oid}, {"not_interested_reasons": 1})
    if user:
        for r in user.get("not_interested_reasons", []):
            if r not in _PREDEFINED_REASONS:
                custom_texts.append(r)

    for doc in db.jobs.find(
        {
            "user_id": str(user_id),
            "status": "not_interested",
            "notes": {"$nin": ["", *list(_PREDEFINED_REASONS)]},
        },
        {"notes": 1},
    ):
        note = (doc.get("notes") or "").strip()
        if note and note not in _PREDEFINED_REASONS:
            custom_texts.append(note)

    keywords: set[str] = set()
    for text in custom_texts:
        for word in _re.split(r"[\s\-_/,.|;:!?()\[\]\"']+", text.lower()):
            word = word.strip("\"'.,;:")
            if len(word) >= 4 and word not in _SKIP_STOPWORDS:
                keywords.add(word)

    return sorted(keywords)

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
        "tags": (
            json.dumps(job.tags[:10])
            if isinstance(job.tags, list)
            else (job.tags or "[]")
        ),
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
    """Save multiple jobs with fuzzy dedup (same company+title within 7 days → keep highest score).
    Returns count of new jobs inserted."""
    from datetime import timedelta

    from pymongo import InsertOne, UpdateOne
    from pymongo.errors import BulkWriteError

    db = _get_db()
    docs = [_build_job_doc(job, score_data, user_id=user_id) for job, score_data in ranked]
    if not docs:
        return 0

    seen_key_to_idx: dict[str, int] = {}
    best_docs: list[dict] = []
    for doc in docs:
        key = (
            f"{(doc.get('company') or '').lower().strip()[:60]}"
            f"|{(doc.get('title') or '').lower().strip()[:80]}"
        )
        if key in seen_key_to_idx:
            idx = seen_key_to_idx[key]
            if doc["score"] > best_docs[idx]["score"]:
                best_docs[idx] = doc
        else:
            seen_key_to_idx[key] = len(best_docs)
            best_docs.append(doc)

    uid_str = str(user_id) if user_id else None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    companies = list({(d.get("company") or "")[:60] for d in best_docs})

    existing_map: dict[str, dict] = {}
    if companies:
        for ex in db.jobs.find(
            {"user_id": uid_str, "company": {"$in": companies}, "created_at": {"$gte": cutoff}},
            {"_id": 1, "company": 1, "title": 1, "score": 1},
        ):
            ex_key = (
                f"{(ex.get('company') or '').lower().strip()[:60]}"
                f"|{(ex.get('title') or '').lower().strip()[:80]}"
            )
            existing_map[ex_key] = ex

    ops = []
    for doc in best_docs:
        key = (
            f"{(doc.get('company') or '').lower().strip()[:60]}"
            f"|{(doc.get('title') or '').lower().strip()[:80]}"
        )
        if key in existing_map:
            ex = existing_map[key]
            if doc["score"] > ex.get("score", 0):
                ops.append(UpdateOne(
                    {"_id": ex["_id"]},
                    {"$set": {"score": doc["score"], "source": doc["source"],
                              "url": doc["url"], "updated_at": doc["updated_at"]}},
                ))
        else:
            ops.append(InsertOne(doc))

    if not ops:
        return 0

    try:
        result = db.jobs.bulk_write(ops, ordered=False)
        return result.inserted_count
    except BulkWriteError as e:
        return e.details.get("nInserted", 0)

def update_job_status(job_id, status: str, notes: str = ""):
    """Update job application status. Tracks applied_at timestamp for follow-up reminders."""
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        now = datetime.now(timezone.utc).isoformat()
        fields = {"status": status, "notes": notes, "updated_at": now}
        if status == "applied":
            fields["applied_at"] = now
        db.jobs.update_one({"_id": oid}, {"$set": fields})

def update_interview_details(job_id, details: dict, user_id=None):
    """Save or update interview scheduling details for a job."""
    db = _get_db()
    oid = _to_object_id(job_id)
    if not oid:
        return False
    query = {"_id": oid}
    if user_id:
        query["user_id"] = str(user_id)
    now = datetime.now(timezone.utc).isoformat()
    result = db.jobs.update_one(
        query,
        {
            "$set": {
                "interview_details": details,
                "status": "interview",
                "updated_at": now,
            }
        },
    )
    return result.modified_count > 0

def update_offer_details(job_id, details: dict, user_id=None):
    """Save or update offer letter details for a job."""
    db = _get_db()
    oid = _to_object_id(job_id)
    if not oid:
        return False
    query = {"_id": oid}
    if user_id:
        query["user_id"] = str(user_id)
    now = datetime.now(timezone.utc).isoformat()
    result = db.jobs.update_one(
        query,
        {
            "$set": {
                "offer_details": details,
                "status": "offer",
                "updated_at": now,
            }
        },
    )
    return result.modified_count > 0

VALID_SORT_FIELDS = {
    "score",
    "date_posted",
    "updated_at",
    "created_at",
    "title",
    "company",
    "salary",
}

def get_jobs(
    status: Optional[str] = None,
    status_in: Optional[list] = None,
    status_nin: Optional[list] = None,
    is_saved: Optional[bool] = None,
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
    if is_saved is True:
        query["is_saved"] = True
    elif is_saved is False:
        query["is_saved"] = {"$ne": True}
    if source:
        query["source"] = source

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

    docs = [_id_str(doc) for doc in cursor]

    now_utc = datetime.now(timezone.utc)
    for doc in docs:
        if doc.get("status") == "applied" and doc.get("applied_at"):
            try:
                applied_dt = datetime.fromisoformat(doc["applied_at"])
                if applied_dt.tzinfo is None:
                    applied_dt = applied_dt.replace(tzinfo=timezone.utc)
                days_elapsed = (now_utc - applied_dt).days
                doc["followup_due"] = days_elapsed >= 7
                doc["days_since_applied"] = days_elapsed
            except Exception:
                doc["followup_due"] = False
                doc["days_since_applied"] = None
        else:
            doc["followup_due"] = False
            doc["days_since_applied"] = None

    return docs, total

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

    all_statuses = [
        "new",
        "saved",
        "applied",
        "interview",
        "offer",
        "rejected",
        "not_interested",
    ]
    stats = {"total": db.jobs.count_documents(base_filter)}
    for s in all_statuses:
        stats[s] = db.jobs.count_documents({**base_filter, "status": s})

    pipeline = [
        {"$match": base_filter},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}},
    ]
    result = list(db.jobs.aggregate(pipeline))
    stats["avg_score"] = result[0]["avg"] if result and result[0]["avg"] else 0

    buckets = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
    score_dist = []
    for i in range(len(buckets) - 1):
        cnt = db.jobs.count_documents(
            {**base_filter, "score": {"$gte": buckets[i], "$lt": buckets[i + 1]}}
        )
        score_dist.append(
            {"label": f"{int(buckets[i]*100)}-{int(buckets[i+1]*100)}%", "count": cnt}
        )
    stats["score_distribution"] = score_dist

    pipeline = [
        {"$match": base_filter},
        {
            "$group": {
                "_id": "$company",
                "count": {"$sum": 1},
                "avg_score": {"$avg": "$score"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    stats["top_companies"] = [
        {
            "name": r["_id"],
            "count": r["count"],
            "avg_score": round(r["avg_score"] * 100),
        }
        for r in db.jobs.aggregate(pipeline)
        if r["_id"]
    ]

    from datetime import timedelta

    today = datetime.now(timezone.utc).date()
    daily = {}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        daily[d] = 0
    pipeline = [
        {
            "$match": {
                **base_filter,
                "created_at": {"$gte": (today - timedelta(days=13)).isoformat()},
            }
        },
        {"$group": {"_id": {"$substr": ["$created_at", 0, 10]}, "count": {"$sum": 1}}},
    ]
    for r in db.jobs.aggregate(pipeline):
        if r["_id"] in daily:
            daily[r["_id"]] = r["count"]
    stats["daily_activity"] = [{"date": d, "count": c} for d, c in daily.items()]

    stats["funnel"] = [
        {"stage": "Discovered", "count": stats["total"]},
        {"stage": "New", "count": stats["new"] + stats.get("saved", 0)},
        {
            "stage": "Applied",
            "count": stats["applied"] + stats["interview"] + stats.get("offer", 0),
        },
        {"stage": "Interview", "count": stats["interview"] + stats.get("offer", 0)},
        {"stage": "Offer", "count": stats.get("offer", 0)},
    ]

    pipeline = [
        {"$match": {**base_filter, "status": {"$in": ["applied", "interview", "offer"]}}},
        {
            "$group": {
                "_id": "$source",
                "applied": {"$sum": 1},
                "interviews": {
                    "$sum": {"$cond": [{"$in": ["$status", ["interview", "offer"]]}, 1, 0]}
                },
            }
        },
        {"$sort": {"applied": -1}},
        {"$limit": 10},
    ]
    stats["source_conversion"] = [
        {
            "source": r["_id"] or "unknown",
            "applied": r["applied"],
            "interviews": r["interviews"],
            "rate": round(r["interviews"] / r["applied"] * 100) if r["applied"] else 0,
        }
        for r in db.jobs.aggregate(pipeline)
    ]

    pipeline = [
        {"$match": {**base_filter, "cover_letter_tone": {"$exists": True, "$ne": None}}},
        {
            "$group": {
                "_id": "$cover_letter_tone",
                "total": {"$sum": 1},
                "interviews": {
                    "$sum": {"$cond": [{"$in": ["$status", ["interview", "offer"]]}, 1, 0]}
                },
            }
        },
    ]
    stats["cover_letter_ab"] = [
        {
            "tone": r["_id"],
            "total": r["total"],
            "interviews": r["interviews"],
            "rate": round(r["interviews"] / r["total"] * 100) if r["total"] else 0,
        }
        for r in db.jobs.aggregate(pipeline)
    ]

    return stats

def log_search_run(
    queries: list[str],
    total_found: int,
    total_matched: int,
    sources: list[str],
    user_id=None,
):
    """Log a search run for analytics."""
    db = _get_db()
    db.search_runs.insert_one(
        {
            "user_id": str(user_id) if user_id else None,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "queries": queries,
            "total_found": total_found,
            "total_matched": total_matched,
            "sources": sources,
        }
    )

init_db()
