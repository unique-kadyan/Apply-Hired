"""Freemium tier resolution + monthly quota enforcement.

Tiers:
  - admin : env-controlled (ADMIN_EMAIL); bypasses every limit and gate
  - pro   : user has an active subscription (subscription.status == "active"
            AND subscription.expires_at > now)
  - free  : default; subject to the monthly limits in FREE_LIMITS

Quota accounting lives in a dedicated `usage` collection, keyed by
(user_id, period, feature). Period is "YYYY-MM" (UTC). Counters are bumped
atomically via $inc + upsert so two concurrent requests can't double-spend.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from middleware import is_admin
from tracker import _get_db, _to_object_id

logger = logging.getLogger(__name__)

# ── Free-tier monthly limits ───────────────────────────────────────────────
FREE_LIMITS = {
    "jobs_visible": 5,            # max jobs the user can see un-blurred per month
    "jobs_applied": 5,            # max bulk-apply / mark-applied per month
    "cover_letters": 1,           # max cover letter generations per month
    "resume_optimizations": 0,    # 0 free; each one costs 50 INR (per-use payment)
    "auto_search": 0,             # auto-search disabled for free entirely
    "chrome_extension": 0,        # autofill API disabled for free entirely
    "pdf_templates_count": 1,     # only 1 basic resume PDF template
}

# Pro tier — what the user gets for the subscription
PRO_LIMITS = {
    "jobs_visible": -1,           # -1 = unlimited
    "jobs_applied": -1,
    "cover_letters": -1,
    "resume_optimizations": -1,
    "auto_search": -1,
    "chrome_extension": 1,        # enabled
    "pdf_templates_count": -1,    # all templates unlocked
}

# The single PDF template free users can use (must match a key in resumePDF.js RENDERERS)
FREE_PDF_TEMPLATE_INDEX = 0

# Per-use price for free users to optimise a resume (₹).
RESUME_OPTIMIZE_PRICE_INR = int(os.environ.get("RESUME_PRICE_INR", "50"))

# Pro subscription price (₹) per billing period.
PRO_MONTHLY_PRICE_INR = int(os.environ.get("PRO_MONTHLY_PRICE_INR", "199"))
PRO_YEARLY_PRICE_INR = int(os.environ.get("PRO_YEARLY_PRICE_INR", "1999"))

# Available Pro plans — keys consumed by the subscribe endpoint
PRO_PLANS = {
    "monthly": {"months": 1, "price_inr": PRO_MONTHLY_PRICE_INR, "label": "Pro Monthly"},
    "yearly":  {"months": 12, "price_inr": PRO_YEARLY_PRICE_INR, "label": "Pro Yearly"},
}


# ──────────────────────────────────────────────────────────────────────────
# Tier resolution
# ──────────────────────────────────────────────────────────────────────────

def _period_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def _subscription_active(sub: dict | None) -> bool:
    if not sub or sub.get("status") != "active":
        return False
    expires = sub.get("expires_at")
    if not expires:
        return False
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            return False
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
    return False


def get_user_tier(user: dict) -> str:
    """Return 'admin' | 'pro' | 'free'."""
    if is_admin(user):
        return "admin"
    sub = user.get("subscription")
    if _subscription_active(sub):
        return "pro"
    return "free"


def get_limits(tier: str) -> dict:
    if tier in ("admin", "pro"):
        return PRO_LIMITS
    return FREE_LIMITS


def is_unlimited(tier: str, feature: str) -> bool:
    if tier == "admin":
        return True
    return get_limits(tier).get(feature, 0) == -1


# ──────────────────────────────────────────────────────────────────────────
# Quota tracking — atomic per-month counters in `usage` collection
# ──────────────────────────────────────────────────────────────────────────

def _usage_doc_filter(user_id, period: str) -> dict:
    return {"user_id": str(user_id), "period": period}


def get_usage(user_id, feature: str, period: Optional[str] = None) -> int:
    """How many units of `feature` the user has consumed this period."""
    db = _get_db()
    period = period or _period_key()
    doc = db.usage.find_one(_usage_doc_filter(user_id, period), {feature: 1})
    return int((doc or {}).get(feature, 0))


def consume_quota(user, feature: str, amount: int = 1) -> tuple[bool, int, int]:
    """Atomically record that the user used `amount` of `feature` this month.

    Returns (allowed, used_after, limit). `allowed=False` means the user's
    monthly cap would be exceeded — call the route's 402 path. Admin/Pro never
    get blocked (limit returned as -1).
    """
    tier = get_user_tier(user)
    limit = get_limits(tier).get(feature, 0)

    if tier == "admin" or limit == -1:
        # Still record usage for analytics, but never block.
        _bump(user["id"], feature, amount)
        return True, 0, -1

    used = get_usage(user["id"], feature)
    if used + amount > limit:
        return False, used, limit

    new_used = _bump(user["id"], feature, amount)
    return True, new_used, limit


def _bump(user_id, feature: str, amount: int) -> int:
    db = _get_db()
    period = _period_key()
    res = db.usage.find_one_and_update(
        _usage_doc_filter(user_id, period),
        {
            "$inc": {feature: amount},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
        return_document=True,  # pymongo: ReturnDocument.AFTER constant; True works on most drivers
    )
    if res is None:
        return amount
    return int(res.get(feature, amount))


# ──────────────────────────────────────────────────────────────────────────
# Visibility window — which jobs is a free user allowed to see un-blurred?
# ──────────────────────────────────────────────────────────────────────────

def get_visible_job_ids(user_id) -> list[str]:
    """Return the list of job IDs already 'unlocked' for this free user this month.

    The first N distinct jobs the user requests/views become 'their' visible
    jobs for the rest of the month. After that, every other job in their list
    is shown blurred.
    """
    db = _get_db()
    period = _period_key()
    doc = db.usage.find_one(_usage_doc_filter(user_id, period), {"visible_job_ids": 1})
    return list((doc or {}).get("visible_job_ids", []))


def unlock_job(user_id, job_id: str) -> tuple[bool, list[str], int]:
    """Add `job_id` to the user's unlocked set for this month if quota remains.
    Returns (unlocked_now, current_unlocked_ids, limit).

    Idempotent — if job_id is already unlocked, returns (True, ids, limit).
    """
    db = _get_db()
    period = _period_key()
    limit = FREE_LIMITS["jobs_visible"]

    current = get_visible_job_ids(user_id)
    if job_id in current:
        return True, current, limit
    if len(current) >= limit:
        return False, current, limit

    db.usage.update_one(
        _usage_doc_filter(user_id, period),
        {
            "$addToSet": {"visible_job_ids": job_id},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )
    return True, current + [job_id], limit


# ──────────────────────────────────────────────────────────────────────────
# Subscription helpers (used by the /api/payment/subscribe webhook)
# ──────────────────────────────────────────────────────────────────────────

def mark_user_pro(user_id, months: int = 1, razorpay_subscription_id: str = "") -> None:
    """Activate Pro for `months` from now (uses 30-day months — good enough for billing)."""
    from datetime import timedelta
    db = _get_db()
    expires = datetime.now(timezone.utc) + timedelta(days=30 * months)
    db.users.update_one(
        {"_id": _to_object_id(user_id)},
        {
            "$set": {
                "subscription": {
                    "status": "active",
                    "plan": f"pro_{months}m",
                    "expires_at": expires.isoformat(),
                    "razorpay_subscription_id": razorpay_subscription_id,
                    "activated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        },
    )
