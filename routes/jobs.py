"""Jobs routes — list, detail, status update, cover letter, apply, auto-apply."""

import json
from datetime import datetime

from flask import Blueprint, request, jsonify

from middleware import login_required, get_user_profile
from scrapers import Job
from cover_letter import generate_cover_letter, check_profile_completeness
from tracker import (
    get_jobs, get_job_by_id, update_job_status, _get_db, _to_object_id,
    get_not_interested_reasons, save_not_interested_reason, update_user_profile,
)

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api")


def _job_to_obj(job: dict) -> Job:
    """Convert a DB row dict to a Job namedtuple for cover letter generation."""
    return Job(
        title=job["title"], company=job["company"], location=job["location"],
        url=job["url"], source=job["source"],
        description=job.get("description", ""),
        tags=json.loads(job.get("tags", "[]")),
    )


def _ensure_cover_letter(job: dict, job_id, profile_data: dict | None = None) -> str:
    """Return existing cover letter or generate + persist a new one."""
    if job.get("cover_letter"):
        return job["cover_letter"]
    letter = generate_cover_letter(_job_to_obj(job), profile_data)
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter}})
    return letter


# ---- List & Detail ---------------------------------------------------------

APPLIED_STATUSES = ["applied", "interview", "offer"]
NOT_INTERESTED_STATUS = "not_interested"
# Statuses excluded from the "Not Applied" tab
_EXCLUDE_FROM_NOT_APPLIED = APPLIED_STATUSES + [NOT_INTERESTED_STATUS]

@jobs_bp.route("/jobs", methods=["GET"])
@login_required
def list_jobs():
    status = request.args.get("status", "")
    tab = request.args.get("tab", "")  # "not_applied" | "applied" | "not_interested" | ""
    min_score = float(request.args.get("min_score", 0))
    source = request.args.get("source", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    status_in = None
    status_nin = None
    sort_by = "score"

    if tab == "not_applied":
        status_nin = _EXCLUDE_FROM_NOT_APPLIED
        sort_by = "date_posted"
    elif tab == "applied":
        status_in = APPLIED_STATUSES
        sort_by = "updated_at"
    elif tab == "not_interested":
        status_in = [NOT_INTERESTED_STATUS]
        sort_by = "updated_at"

    jobs, total = get_jobs(
        status=status or None,
        status_in=status_in,
        status_nin=status_nin,
        min_score=min_score,
        source=source or None,
        sort_by=sort_by,
        page=page,
        per_page=per_page,
        user_id=request.user["id"],
    )
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify({"jobs": jobs, "total": total, "page": page, "per_page": per_page})


# ---- Not-Interested Reasons -----------------------------------------------

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


@jobs_bp.route("/jobs/<job_id>", methods=["GET"])
@login_required
def get_job(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["tags"] = json.loads(job.get("tags", "[]"))
    job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify(job)


# ---- Status & Cover Letter -------------------------------------------------

@jobs_bp.route("/jobs/<job_id>/status", methods=["PUT", "POST"])
@login_required
def change_status(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json()
    update_job_status(job_id, data.get("status", "new"), data.get("notes", ""))
    return jsonify({"message": f"Job #{job_id} updated to '{data.get('status')}'"})


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
    """Generate (or regenerate) a cover letter using the user's real profile."""
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    profile = get_user_profile(request.user)
    letter = generate_cover_letter(_job_to_obj(job), profile)
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter}})
    return jsonify({"cover_letter": letter})


# ---- Profile completeness check -------------------------------------------

@jobs_bp.route("/jobs/profile-check", methods=["GET"])
@login_required
def profile_check():
    """Return which required fields are missing for cover letter / auto-apply."""
    profile = get_user_profile(request.user)
    result = check_profile_completeness(profile)
    return jsonify(result)


# ---- Clear jobs -----------------------------------------------------------

@jobs_bp.route("/jobs/clear", methods=["POST"])
@login_required
def clear_jobs():
    """Delete non-applied jobs. Keeps applied, interview, and offer jobs."""
    keep_statuses = {"applied", "interview", "offer"}
    db = _get_db()
    result = db.jobs.delete_many({
        "user_id": str(request.user["id"]),
        "status": {"$nin": list(keep_statuses)},
    })
    return jsonify({"deleted": result.deleted_count, "kept": list(keep_statuses)})


# ---- Mark applied by URL (used by Chrome Extension) ----------------------

@jobs_bp.route("/mark-applied-by-url", methods=["POST"])
@login_required
def mark_applied_by_url():
    """Mark a job as applied by matching its URL. Used by Chrome Extension after form submission."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    db = _get_db()
    # Find job by URL for this user
    result = db.jobs.update_many(
        {"user_id": str(request.user["id"]), "url": {"$regex": url.split("?")[0][:100]}},
        {"$set": {"status": "applied", "updated_at": datetime.now().isoformat(),
                  "notes": f"Applied via Chrome Extension on {datetime.now().strftime('%Y-%m-%d %H:%M')}"}},
    )
    return jsonify({"matched": result.modified_count})


# ---- Apply & Auto-Apply ---------------------------------------------------

@jobs_bp.route("/apply", methods=["POST"])
@login_required
def apply_jobs():
    data = request.get_json()
    job_ids = data.get("job_ids", [])
    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    profile = get_user_profile(request.user)
    results = []
    for jid in job_ids:
        try:
            job = get_job_by_id(jid, user_id=request.user["id"])
            if not job or job["status"] == "applied":
                continue
            _ensure_cover_letter(job, jid, profile)
            update_job_status(jid, "applied",
                              f"Applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            results.append({"id": jid, "status": "applied"})
        except Exception:
            continue
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

    # Load and optionally patch profile
    profile = get_user_profile(request.user)
    patch = data.get("profile_patch", {})
    if patch:
        # Merge patch fields into profile
        for key, val in patch.items():
            if key == "skills_text":
                # Convert comma-separated skills text into profile skills dict
                skill_list = [s.strip() for s in val.split(",") if s.strip()]
                if skill_list:
                    profile.setdefault("skills", {})["other"] = skill_list
            else:
                profile[key] = val
        # Persist patched profile so user doesn't have to fill it again
        update_user_profile(request.user["id"], profile)

    # Check completeness after patch
    check = check_profile_completeness(profile)
    if not check["is_complete"]:
        return jsonify({
            "needs_info": True,
            "missing": check["missing"],
            "warnings": check["warnings"],
        }), 422

    details = []
    for jid in job_ids:
        try:
            job = get_job_by_id(jid, user_id=request.user["id"])
            if not job:
                continue
            # Force-regenerate with real profile (ignore cached generic letter)
            letter = generate_cover_letter(_job_to_obj(job), profile)
            db = _get_db()
            oid = _to_object_id(jid)
            if oid:
                db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter}})
            update_job_status(jid, "applied",
                              f"Applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            details.append({
                "id": job["id"], "title": job["title"], "company": job["company"],
                "url": job["url"], "cover_letter": letter, "status": "ready",
            })
        except Exception:
            continue

    return jsonify({
        "total": len(details),
        "opened": len(details),
        "auto_filled": 0,
        "failed": 0,
        "details": details,
    })
