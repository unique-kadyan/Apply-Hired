"""Jobs routes — list, detail, status update, cover letter, apply, auto-apply."""

import json
from datetime import datetime

from flask import Blueprint, request, jsonify

from middleware import login_required
from scrapers import Job
from cover_letter import generate_cover_letter
from tracker import (
    get_jobs, get_job_by_id, update_job_status, _get_conn,
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


def _ensure_cover_letter(job: dict, job_id: int) -> str:
    """Generate and persist a cover letter if one doesn't exist."""
    if job.get("cover_letter"):
        return job["cover_letter"]
    letter = generate_cover_letter(_job_to_obj(job))
    conn = _get_conn()
    conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
    conn.commit()
    conn.close()
    return letter


# ---- List & Detail ---------------------------------------------------------

@jobs_bp.route("/jobs", methods=["GET"])
@login_required
def list_jobs():
    status = request.args.get("status", "")
    min_score = float(request.args.get("min_score", 0))
    source = request.args.get("source", "")
    limit = int(request.args.get("limit", 100))

    jobs = get_jobs(
        status=status or None, min_score=min_score,
        source=source or None, limit=limit,
        user_id=request.user["id"],
    )
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify(jobs)


@jobs_bp.route("/jobs/<int:job_id>", methods=["GET"])
@login_required
def get_job(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["tags"] = json.loads(job.get("tags", "[]"))
    job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify(job)


# ---- Status & Cover Letter -------------------------------------------------

@jobs_bp.route("/jobs/<int:job_id>/status", methods=["PUT"])
@login_required
def change_status(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json()
    update_job_status(job_id, data.get("status", "new"), data.get("notes", ""))
    return jsonify({"message": f"Job #{job_id} updated to '{data.get('status')}'"})


@jobs_bp.route("/jobs/<int:job_id>/cover-letter", methods=["POST"])
@login_required
def gen_cover_letter(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    letter = generate_cover_letter(_job_to_obj(job))
    conn = _get_conn()
    conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
    conn.commit()
    conn.close()
    return jsonify({"cover_letter": letter})


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
    from auto_apply import auto_apply_batch

    data = request.get_json()
    job_ids = data.get("job_ids", [])
    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    jobs_with_letters = []
    for jid in job_ids:
        try:
            job = get_job_by_id(int(jid), user_id=request.user["id"])
            if not job:
                continue
            letter = _ensure_cover_letter(job, int(jid))
            jobs_with_letters.append({
                "id": job["id"], "title": job["title"], "company": job["company"],
                "url": job["url"], "cover_letter": letter,
                "description": job.get("description", ""),
            })
        except Exception:
            continue

    results = auto_apply_batch(jobs_with_letters)

    for detail in results.get("details", []):
        if detail["status"] in ("opened", "auto_filled", "opened_browser"):
            update_job_status(
                detail["id"], "applied",
                f"Auto-applied on {datetime.now().strftime('%Y-%m-%d %H:%M')} ({detail['status']})",
            )
    return jsonify(results)
