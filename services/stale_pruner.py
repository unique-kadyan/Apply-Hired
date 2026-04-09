"""Stale job pruner — weekly background task that marks expired job listings.

A job is considered stale when its URL returns HTTP 404 or 410.
Only jobs in passive statuses (new, saved, fresh new) older than 30 days
are checked to avoid hitting active/applied jobs or recent listings.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_CHECK_STATUSES = {"new", "saved", "fresh new"}
_MIN_AGE_DAYS   = 30   # only check jobs at least this old
_MAX_PER_RUN    = 60   # cap HTTP requests per scheduled run
_REQUEST_TIMEOUT = 8   # seconds per HEAD request


def prune_stale_jobs(user_id=None, max_check: int = _MAX_PER_RUN) -> int:
    """HEAD-check job URLs and mark expired (404/410) ones.

    Args:
        user_id: Scope to a single user; None = all users.
        max_check: Maximum number of URLs to probe in this run.

    Returns:
        Count of jobs marked as expired.
    """
    from tracker import _get_db

    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_MIN_AGE_DAYS)).isoformat()

    query: dict = {
        "status": {"$in": list(_CHECK_STATUSES)},
        "created_at": {"$lte": cutoff},
        "url_checked_at": {"$exists": False},  # not yet probed
    }
    if user_id is not None:
        query["user_id"] = str(user_id)

    jobs = list(db.jobs.find(query, {"_id": 1, "url": 1}).limit(max_check))
    now = datetime.now(timezone.utc).isoformat()
    marked = 0

    for job in jobs:
        url = (job.get("url") or "").strip()
        if not url:
            continue
        try:
            resp = requests.head(url, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
            is_expired = resp.status_code in (404, 410)
            update_fields: dict = {"url_checked_at": now}
            if is_expired:
                update_fields["status"] = "expired"
                marked += 1
            db.jobs.update_one({"_id": job["_id"]}, {"$set": update_fields})
        except Exception:
            # Network error — record the check attempt so we don't retry indefinitely
            db.jobs.update_one({"_id": job["_id"]}, {"$set": {"url_checked_at": now}})

    logger.info(f"Stale pruner: checked {len(jobs)}, marked {marked} expired")
    return marked
