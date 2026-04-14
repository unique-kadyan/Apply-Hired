"""Jobs routes — list, detail, status update, cover letter, apply, auto-apply."""

import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from cover_letter import check_profile_completeness, generate_cover_letter
from middleware import get_user_profile, login_required
from scrapers import Job
from services.events import publish
from services.tier import (
    FREE_LIMITS,
    consume_quota,
    get_user_tier,
    get_visible_job_ids,
    unlock_job,
)
from tracker import (
    _get_db,
    _to_object_id,
    delete_not_interested_reason,
    get_job_by_id,
    get_jobs,
    get_not_interested_reasons,
    get_skip_filter_keywords,
    save_not_interested_reason,
    update_interview_details,
    update_job_status,
    update_offer_details,
    update_user_profile,
)

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api")


def _notify_jobs_changed(reason: str, job_id: str | None = None, status: str | None = None) -> None:
    """Push a jobs_changed event so connected SSE clients refetch their lists."""
    try:
        uid = str(request.user["id"])
    except Exception:
        return
    payload: dict = {"reason": reason}
    if job_id:
        payload["job_id"] = job_id
    if status:
        payload["status"] = status
    publish(uid, "jobs_changed", payload)
    if job_id:
        publish(uid, "job_updated", payload)

def _job_to_obj(job: dict) -> Job:
    """Convert a DB row dict to a Job namedtuple for cover letter generation."""
    return Job(
        title=job["title"],
        company=job["company"],
        location=job["location"],
        url=job["url"],
        source=job["source"],
        description=job.get("description", ""),
        tags=json.loads(job.get("tags", "[]")),
    )

def _ensure_cover_letter(job: dict, job_id, profile_data: dict | None = None) -> str:
    """Return existing cover letter or generate + persist a new one."""
    if job.get("cover_letter"):
        return job["cover_letter"]
    letter, tone = generate_cover_letter(_job_to_obj(job), profile_data)
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter, "cover_letter_tone": tone}})
    return letter

APPLIED_STATUSES = ["applied", "interview", "offer"]
NOT_INTERESTED_STATUS = "not_interested"
_EXCLUDE_FROM_NOT_APPLIED = APPLIED_STATUSES + [NOT_INTERESTED_STATUS]

@jobs_bp.route("/jobs", methods=["GET"])
@login_required
def list_jobs():
    status = request.args.get("status", "")
    tab = request.args.get("tab", "")
    min_score = float(request.args.get("min_score", 0))
    source = request.args.get("source", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "")
    sort_dir = request.args.get("sort_dir", "desc")

    status_in = None
    status_nin = None
    is_saved = None
    include_cleared = False
    history_or = None
    default_sort = "score"

    if tab == "not_applied":
        status_nin = _EXCLUDE_FROM_NOT_APPLIED
        is_saved = False
        default_sort = "date_posted"
    elif tab == "applied":
        status_in = APPLIED_STATUSES
        default_sort = "updated_at"
    elif tab == "not_interested":
        status_in = [NOT_INTERESTED_STATUS]
        default_sort = "updated_at"
    elif tab == "saved":
        is_saved = True
        status_nin = _EXCLUDE_FROM_NOT_APPLIED
        default_sort = "updated_at"
    elif tab == "history":
        include_cleared = True
        history_or = [
            {"status": {"$in": APPLIED_STATUSES + [NOT_INTERESTED_STATUS]}},
            {"cleared": True},
        ]
        default_sort = "updated_at"

    from tracker import VALID_SORT_FIELDS

    final_sort = sort_by if sort_by in VALID_SORT_FIELDS else default_sort

    jobs, total = get_jobs(
        status=status or None,
        status_in=status_in,
        status_nin=status_nin,
        is_saved=is_saved,
        include_cleared=include_cleared,
        history_or=history_or,
        min_score=min_score,
        source=source or None,
        sort_by=final_sort,
        sort_dir=sort_dir,
        search=search or None,
        page=page,
        per_page=per_page,
        user_id=request.user["id"],
    )
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))

    # ── Free-tier visibility cap: 5 unlocked jobs per month, rest blurred ──
    tier = get_user_tier(request.user)
    visible_count_unlocked = 0
    if tier == "free":
        unlocked_ids = set(get_visible_job_ids(request.user["id"]))
        visible_count_unlocked = len(unlocked_ids)
        slots_left = max(0, FREE_LIMITS["jobs_visible"] - visible_count_unlocked)
        for job in jobs:
            jid = str(job.get("id", ""))
            if jid in unlocked_ids:
                continue  # already unlocked
            if slots_left > 0:
                # Auto-unlock the highest-ranked jobs they haven't seen yet,
                # up to the free-tier monthly cap.
                ok, _ids, _lim = unlock_job(request.user["id"], jid)
                if ok:
                    unlocked_ids.add(jid)
                    slots_left -= 1
                    visible_count_unlocked += 1
                    continue
            # Beyond the cap → return a stripped, blurred placeholder so the
            # client can render a row with no link, no actionable data.
            job["blurred"] = True
            job["title"] = "Premium job — upgrade to Pro to unlock"
            job["company"] = ""
            job["location"] = ""
            job["salary"] = ""
            job["description"] = ""
            job["url"] = ""
            job["tags"] = []
            job["score_details"] = {}

    return jsonify({
        "jobs": jobs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "tier": tier,
        "free_visible_unlocked": visible_count_unlocked if tier == "free" else None,
        "free_visible_limit": FREE_LIMITS["jobs_visible"] if tier == "free" else None,
    })

@jobs_bp.route("/jobs/tab-counts", methods=["GET"])
@login_required
def tab_counts():
    """Return the total job count for each tab in one query."""
    db = _get_db()
    uid = str(request.user["id"])
    not_applied = db.jobs.count_documents(
        {"user_id": uid, "status": {"$nin": _EXCLUDE_FROM_NOT_APPLIED}, "is_saved": {"$ne": True}, "cleared": {"$ne": True}}
    )
    applied = db.jobs.count_documents(
        {"user_id": uid, "status": {"$in": APPLIED_STATUSES}}
    )
    not_interested = db.jobs.count_documents(
        {"user_id": uid, "status": NOT_INTERESTED_STATUS}
    )
    saved = db.jobs.count_documents(
        {"user_id": uid, "is_saved": True, "status": {"$nin": _EXCLUDE_FROM_NOT_APPLIED}, "cleared": {"$ne": True}}
    )
    history = db.jobs.count_documents({"user_id": uid, "$or": [
        {"status": {"$in": APPLIED_STATUSES + [NOT_INTERESTED_STATUS]}},
        {"cleared": True},
    ]})
    return jsonify(
        {
            "not_applied": not_applied,
            "applied": applied,
            "not_interested": not_interested,
            "saved": saved,
            "history": history,
        }
    )

@jobs_bp.route("/jobs/not-interested-reasons", methods=["GET"])
@login_required
def get_ni_reasons():
    """Return this user's saved custom not-interested reasons."""
    reasons = get_not_interested_reasons(request.user["id"])
    return jsonify({"reasons": reasons})

@jobs_bp.route("/jobs/not-interested-reasons", methods=["POST"])
@login_required
def add_ni_reason():
    """Save a new custom not-interested reason for this user."""
    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "reason is required"}), 400
    updated = save_not_interested_reason(request.user["id"], reason)
    return jsonify({"reasons": updated})

@jobs_bp.route("/jobs/not-interested-reasons/delete", methods=["POST"])
@login_required
def remove_ni_reason():
    """Remove a specific not-interested reason (and its derived skip keywords)."""
    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "reason is required"}), 400
    updated = delete_not_interested_reason(request.user["id"], reason)
    return jsonify({"reasons": updated})

@jobs_bp.route("/jobs/skip-keywords", methods=["GET"])
@login_required
def get_skip_keywords_route():
    """Return the derived skip keywords from user's not-interested reasons (for display only)."""
    from tracker import _PREDEFINED_REASONS

    reasons = get_not_interested_reasons(request.user["id"])
    custom_reasons = [r for r in reasons if r not in _PREDEFINED_REASONS]
    keywords = get_skip_filter_keywords(request.user["id"])
    return jsonify({"keywords": keywords, "custom_reasons": custom_reasons})

@jobs_bp.route("/jobs/<job_id>", methods=["GET"])
@login_required
def get_job(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Free tier: detail access requires the job to be in this user's unlocked set,
    # OR opening it should atomically unlock it (consuming a slot).
    tier = get_user_tier(request.user)
    if tier == "free":
        ok, _ids, limit = unlock_job(request.user["id"], str(job_id))
        if not ok:
            return jsonify({
                "error": "Free plan limit reached",
                "message": f"You can view {limit} jobs per month on the free plan. Upgrade to Pro for unlimited access.",
                "tier": "free",
                "blurred": True,
            }), 402

    job["tags"] = json.loads(job.get("tags", "[]"))
    job["score_details"] = json.loads(job.get("score_details", "{}"))

    # Free tier: AI score detail is intentionally hidden — show overall match only.
    if tier == "free":
        job["score_details"] = {}
        job["ai_reasons"] = []
        job["ai_missing_skills"] = []
    return jsonify(job)

@jobs_bp.route("/jobs/<job_id>/status", methods=["PUT", "POST"])
@login_required
def change_status(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json()
    new_status = data.get("status", "new")
    update_job_status(job_id, new_status, data.get("notes", ""))
    if new_status in APPLIED_STATUSES + [NOT_INTERESTED_STATUS]:
        db = _get_db()
        oid = _to_object_id(job_id)
        if oid:
            db.jobs.update_one({"_id": oid}, {"$set": {"is_saved": False}})
    _notify_jobs_changed("status_change", job_id=job_id, status=new_status)
    return jsonify({"message": f"Job #{job_id} updated to '{new_status}'"})

@jobs_bp.route("/jobs/<job_id>/save", methods=["POST"])
@login_required
def save_job(job_id):
    """Bookmark a job — moves it to the Saved tab, hides from Not Applied."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    db = _get_db()
    oid = _to_object_id(job_id)
    db.jobs.update_one({"_id": oid}, {"$set": {"is_saved": True}})
    _notify_jobs_changed("saved", job_id=job_id)
    return jsonify({"saved": True})

@jobs_bp.route("/jobs/<job_id>/unsave", methods=["POST"])
@login_required
def unsave_job(job_id):
    """Remove bookmark — job returns to Not Applied."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    db = _get_db()
    oid = _to_object_id(job_id)
    db.jobs.update_one({"_id": oid}, {"$set": {"is_saved": False}})
    _notify_jobs_changed("unsaved", job_id=job_id)
    return jsonify({"saved": False})

@jobs_bp.route("/jobs/<job_id>/cover-letter", methods=["GET"])
@login_required
def get_cover_letter(job_id):
    """Return the stored cover letter (if any) without regenerating."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"cover_letter": job.get("cover_letter") or ""})

@jobs_bp.route("/jobs/<job_id>/cover-letter", methods=["POST"])
@login_required
def gen_cover_letter(job_id):
    """Generate (or regenerate) a cover letter using the user's real profile.
    Free tier: 1 cover letter per month."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404

    tier = get_user_tier(request.user)
    if tier == "free":
        ok, used, limit = consume_quota(request.user, "cover_letters", amount=1)
        if not ok:
            return jsonify({
                "error": f"Free plan limit reached: {used}/{limit} cover letter(s) used this month. Upgrade to Pro for unlimited generation.",
                "used": used,
                "limit": limit,
                "tier": "free",
            }), 402

    profile = get_user_profile(request.user)
    letter, tone = generate_cover_letter(_job_to_obj(job), profile)
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter, "cover_letter_tone": tone}})
    return jsonify({"cover_letter": letter})

@jobs_bp.route("/jobs/profile-check", methods=["GET"])
@login_required
def profile_check():
    """Return which required fields are missing for cover letter / auto-apply."""
    profile = get_user_profile(request.user)
    result = check_profile_completeness(profile)
    return jsonify(result)

@jobs_bp.route("/jobs/<job_id>/interview", methods=["PUT", "POST"])
@login_required
def save_interview(job_id):
    """Save interview scheduling details for a job."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json() or {}
    details = {
        "round": data.get("round", ""),
        "date": data.get("date", ""),
        "time": data.get("time", ""),
        "timezone": data.get("timezone", ""),
        "interviewer": data.get("interviewer", ""),
        "meeting_link": data.get("meeting_link", ""),
        "platform": data.get("platform", ""),
        "notes": data.get("notes", ""),
        "saved_at": datetime.now().isoformat(),
    }
    ok = update_interview_details(job_id, details, user_id=request.user["id"])
    if not ok:
        return jsonify({"error": "Update failed"}), 500
    _notify_jobs_changed("interview_updated", job_id=job_id)
    return jsonify({"message": "Interview details saved", "interview_details": details})

@jobs_bp.route("/jobs/<job_id>/offer", methods=["PUT", "POST"])
@login_required
def save_offer(job_id):
    """Save offer letter details for a job."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json() or {}
    details = {
        "salary": data.get("salary", ""),
        "currency": data.get("currency", ""),
        "joining_date": data.get("joining_date", ""),
        "deadline": data.get("deadline", ""),
        "benefits": data.get("benefits", ""),
        "location": data.get("location", ""),
        "offer_text": data.get("offer_text", ""),
        "notes": data.get("notes", ""),
        "saved_at": datetime.now().isoformat(),
    }
    ok = update_offer_details(job_id, details, user_id=request.user["id"])
    if not ok:
        return jsonify({"error": "Update failed"}), 500
    _notify_jobs_changed("offer_updated", job_id=job_id)
    return jsonify({"message": "Offer details saved", "offer_details": details})

@jobs_bp.route("/jobs/clear", methods=["POST"])
@login_required
def clear_jobs():
    """Mark non-applied jobs as cleared (hidden from view forever). Never deletes from DB."""
    keep_statuses = {"applied", "interview", "offer"}
    db = _get_db()
    result = db.jobs.update_many(
        {
            "user_id": str(request.user["id"]),
            "status": {"$nin": list(keep_statuses)},
            "cleared": {"$ne": True},
        },
        {"$set": {"cleared": True, "updated_at": datetime.now().isoformat()}},
    )
    if result.modified_count:
        _notify_jobs_changed("cleared")
    return jsonify({"cleared": result.modified_count, "kept": list(keep_statuses)})

@jobs_bp.route("/mark-applied-by-url", methods=["POST"])
@login_required
def mark_applied_by_url():
    """Mark a job as applied by matching its URL. Used by Chrome Extension after form submission."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    db = _get_db()
    result = db.jobs.update_many(
        {
            "user_id": str(request.user["id"]),
            "url": {"$regex": url.split("?")[0][:100]},
        },
        {
            "$set": {
                "status": "applied",
                "updated_at": datetime.now().isoformat(),
                "notes": f"Applied via Chrome Extension on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            }
        },
    )
    if result.modified_count:
        _notify_jobs_changed("applied_via_extension")
    return jsonify({"matched": result.modified_count})

@jobs_bp.route("/apply", methods=["POST"])
@login_required
def apply_jobs():
    data = request.get_json()
    job_ids = data.get("job_ids", [])
    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    # Free tier: 5 applications per month total. Reserve quota up front.
    tier = get_user_tier(request.user)
    if tier == "free":
        ok, used, limit = consume_quota(request.user, "jobs_applied", amount=len(job_ids))
        if not ok:
            return jsonify({
                "error": f"Free plan limit reached: {used}/{limit} applications used this month. Upgrade to Pro for unlimited applications.",
                "used": used,
                "limit": limit,
                "tier": "free",
            }), 402

    profile = get_user_profile(request.user)
    results = []
    for jid in job_ids:
        try:
            job = get_job_by_id(jid, user_id=request.user["id"])
            if not job or job["status"] == "applied":
                continue
            _ensure_cover_letter(job, jid, profile)
            update_job_status(
                jid,
                "applied",
                f"Applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            )
            results.append({"id": jid, "status": "applied"})
        except Exception:
            continue
    if results:
        _notify_jobs_changed("bulk_apply")
    return jsonify({"applied": len(results), "results": results})

@jobs_bp.route("/auto-apply", methods=["POST"])
@login_required
def auto_apply():
    """
    Generate cover letters using the user's real profile and return job URLs.

    Accepts optional `profile_patch` dict to fill in missing fields on the fly
    (those fields are also persisted to the user's profile).
    """
    data = request.get_json() or {}
    job_ids = data.get("job_ids", [])
    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    profile = get_user_profile(request.user)
    patch = data.get("profile_patch", {})
    if patch:
        for key, val in patch.items():
            if key == "skills_text":
                skill_list = [s.strip() for s in val.split(",") if s.strip()]
                if skill_list:
                    profile.setdefault("skills", {})["other"] = skill_list
            else:
                profile[key] = val
        update_user_profile(request.user["id"], profile)

    check = check_profile_completeness(profile)
    if not check["is_complete"]:
        return (
            jsonify(
                {
                    "needs_info": True,
                    "missing": check["missing"],
                    "warnings": check["warnings"],
                }
            ),
            422,
        )

    details = []
    for jid in job_ids:
        try:
            job = get_job_by_id(jid, user_id=request.user["id"])
            if not job:
                continue
            letter, tone = generate_cover_letter(_job_to_obj(job), profile)
            db = _get_db()
            oid = _to_object_id(jid)
            if oid:
                db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter, "cover_letter_tone": tone}})
            details.append(
                {
                    "id": job["id"],
                    "title": job["title"],
                    "company": job["company"],
                    "url": job["url"],
                    "cover_letter": letter,
                    "status": "ready",
                }
            )
        except Exception:
            continue

    return jsonify(
        {
            "total": len(details),
            "opened": len(details),
            "auto_filled": 0,
            "failed": 0,
            "details": details,
        }
    )
