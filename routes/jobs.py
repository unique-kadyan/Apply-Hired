"""Jobs routes — list, detail, status update, cover letter, apply, auto-apply."""

import json
from datetime import datetime

from flask import Blueprint, request, jsonify

from middleware import login_required
from scrapers import Job
from cover_letter import generate_cover_letter
from tracker import (
    get_jobs, get_job_by_id, update_job_status, _get_db, _to_object_id,
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


def _ensure_cover_letter(job: dict, job_id) -> str:
    """Generate and persist a cover letter if one doesn't exist."""
    if job.get("cover_letter"):
        return job["cover_letter"]
    letter = generate_cover_letter(_job_to_obj(job))
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter}})
    return letter


# ---- List & Detail ---------------------------------------------------------

@jobs_bp.route("/jobs", methods=["GET"])
@login_required
def list_jobs():
    status = request.args.get("status", "")
    min_score = float(request.args.get("min_score", 0))
    source = request.args.get("source", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    jobs, total = get_jobs(
        status=status or None, min_score=min_score,
        source=source or None, page=page, per_page=per_page,
        user_id=request.user["id"],
    )
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify({"jobs": jobs, "total": total, "page": page, "per_page": per_page})


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


@jobs_bp.route("/jobs/<job_id>/cover-letter", methods=["POST"])
@login_required
def gen_cover_letter(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    letter = generate_cover_letter(_job_to_obj(job))
    db = _get_db()
    oid = _to_object_id(job_id)
    if oid:
        db.jobs.update_one({"_id": oid}, {"$set": {"cover_letter": letter}})
    return jsonify({"cover_letter": letter})


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

    results = []
    for jid in job_ids:
        try:
            job = get_job_by_id(int(jid), user_id=request.user["id"])
            if not job or job["status"] == "applied":
                continue
            _ensure_cover_letter(job, int(jid))
            update_job_status(int(jid), "applied",
                              f"Applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            results.append({"id": jid, "status": "applied"})
        except Exception:
            continue
    return jsonify({"applied": len(results), "results": results})


@jobs_bp.route("/auto-apply", methods=["POST"])
@login_required
def auto_apply():
    """Generate cover letters and return job URLs for the frontend to open."""
    data = request.get_json()
    job_ids = data.get("job_ids", [])
    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    details = []
    for jid in job_ids:
        try:
            job = get_job_by_id(jid, user_id=request.user["id"])
            if not job:
                continue
            letter = _ensure_cover_letter(job, jid)
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
