"""Flask REST API backend for Job Application Bot."""

import os
import json
import threading
import webbrowser
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory

from config import PROFILE, LOCATION_PREFERENCES
from scrapers import search_all_boards, ALL_SCRAPERS, Job
from matcher import rank_jobs
from cover_letter import generate_cover_letter
from resume_parser import parse_resume
from tracker import (
    init_db, save_job, get_jobs, get_stats, get_job_by_id,
    update_job_status, log_search_run,
)

app = Flask(__name__, static_folder="frontend/build", static_url_path="")
app.secret_key = os.urandom(24)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")

# In-memory state
search_status = {"running": False, "message": "", "progress": 0}
current_profile = dict(PROFILE)  # mutable copy


# ---------------------------------------------------------------------------
# Serve React app
# ---------------------------------------------------------------------------

@app.route("/")
def serve_react():
    return send_from_directory(app.static_folder, "index.html")

@app.errorhandler(404)
def not_found(e):
    # SPA fallback — serve index.html for all unknown routes
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# API: Profile
# ---------------------------------------------------------------------------

@app.route("/api/profile", methods=["GET"])
def api_get_profile():
    return jsonify(current_profile)

@app.route("/api/profile", methods=["PUT"])
def api_update_profile():
    global current_profile
    data = request.get_json()
    if data:
        current_profile.update(data)
    return jsonify(current_profile)

@app.route("/api/profile/upload-resume", methods=["POST"])
def api_upload_resume():
    global current_profile
    if "resume" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(filepath)

    try:
        parsed = parse_resume(filepath)
        # Merge parsed data into current profile
        for key, value in parsed.items():
            if value:  # only overwrite if parsed value is non-empty
                if isinstance(value, dict) and key in current_profile:
                    # Merge skills dicts
                    if isinstance(current_profile[key], dict):
                        for k, v in value.items():
                            if v:
                                current_profile[key][k] = v
                    else:
                        current_profile[key] = value
                else:
                    current_profile[key] = value

        return jsonify({
            "message": "Resume parsed successfully!",
            "profile": current_profile,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# API: Jobs
# ---------------------------------------------------------------------------

@app.route("/api/jobs", methods=["GET"])
def api_get_jobs():
    status = request.args.get("status", "")
    min_score = float(request.args.get("min_score", 0))
    source = request.args.get("source", "")
    limit = int(request.args.get("limit", 100))

    jobs = get_jobs(
        status=status or None,
        min_score=min_score,
        source=source or None,
        limit=limit,
    )
    # Parse JSON fields
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))

    return jsonify(jobs)


@app.route("/api/jobs/<int:job_id>", methods=["GET"])
def api_get_job(job_id):
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["tags"] = json.loads(job.get("tags", "[]"))
    job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify(job)


@app.route("/api/jobs/<int:job_id>/status", methods=["PUT"])
def api_update_job_status(job_id):
    data = request.get_json()
    status = data.get("status", "new")
    notes = data.get("notes", "")
    update_job_status(job_id, status, notes)
    return jsonify({"message": f"Job #{job_id} updated to '{status}'"})


@app.route("/api/jobs/<int:job_id>/cover-letter", methods=["POST"])
def api_generate_cover_letter(job_id):
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job_obj = Job(
        title=job["title"],
        company=job["company"],
        location=job["location"],
        url=job["url"],
        source=job["source"],
        description=job.get("description", ""),
        tags=json.loads(job.get("tags", "[]")),
    )
    letter = generate_cover_letter(job_obj)

    from tracker import _get_conn
    conn = _get_conn()
    conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
    conn.commit()
    conn.close()

    return jsonify({"cover_letter": letter})


@app.route("/api/apply", methods=["POST"])
def api_apply_jobs():
    """Mark jobs as applied (track only, no browser)."""
    data = request.get_json()
    job_ids = data.get("job_ids", [])

    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    results = []
    for job_id in job_ids:
        try:
            job = get_job_by_id(int(job_id))
            if not job or job["status"] == "applied":
                continue

            if not job.get("cover_letter"):
                job_obj = Job(
                    title=job["title"], company=job["company"], location=job["location"],
                    url=job["url"], source=job["source"],
                    description=job.get("description", ""),
                    tags=json.loads(job.get("tags", "[]")),
                )
                letter = generate_cover_letter(job_obj)
                from tracker import _get_conn
                conn = _get_conn()
                conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
                conn.commit()
                conn.close()

            update_job_status(int(job_id), "applied",
                              f"Applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            results.append({"id": job_id, "status": "applied"})
        except Exception:
            continue

    return jsonify({"applied": len(results), "results": results})


@app.route("/api/auto-apply", methods=["POST"])
def api_auto_apply():
    """Auto-apply: opens job pages in browser, auto-fills forms, generates cover letters."""
    from auto_apply import auto_apply_batch

    data = request.get_json()
    job_ids = data.get("job_ids", [])

    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    # Prepare jobs with cover letters
    jobs_with_letters = []
    for job_id in job_ids:
        try:
            job = get_job_by_id(int(job_id))
            if not job:
                continue

            # Generate cover letter if missing
            if not job.get("cover_letter"):
                job_obj = Job(
                    title=job["title"], company=job["company"], location=job["location"],
                    url=job["url"], source=job["source"],
                    description=job.get("description", ""),
                    tags=json.loads(job.get("tags", "[]")),
                )
                letter = generate_cover_letter(job_obj)
                from tracker import _get_conn
                conn = _get_conn()
                conn.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", (letter, job_id))
                conn.commit()
                conn.close()
                job["cover_letter"] = letter

            jobs_with_letters.append({
                "id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "url": job["url"],
                "cover_letter": job.get("cover_letter", ""),
                "description": job.get("description", ""),
            })
        except Exception:
            continue

    # Run auto-apply
    results = auto_apply_batch(jobs_with_letters)

    # Update status for successfully opened jobs
    for detail in results.get("details", []):
        if detail["status"] in ("opened", "auto_filled", "opened_browser"):
            update_job_status(
                detail["id"], "applied",
                f"Auto-applied on {datetime.now().strftime('%Y-%m-%d %H:%M')} ({detail['status']})"
            )

    return jsonify(results)


# ---------------------------------------------------------------------------
# API: Search
# ---------------------------------------------------------------------------

@app.route("/api/search", methods=["POST"])
def api_search():
    if search_status["running"]:
        return jsonify({"error": "A search is already running"}), 409

    data = request.get_json() or {}
    search_params = {
        "job_title": data.get("job_title", ""),
        "skills": data.get("skills", []),
        "location": data.get("location", "remote"),
        "country": data.get("country", LOCATION_PREFERENCES.get("default_country", "India")),
        "levels": data.get("levels", []),
        "min_score": data.get("min_score", 0.3),
        "min_salary": data.get("min_salary", 0),
    }

    thread = threading.Thread(target=_run_search_background, args=(search_params,), daemon=True)
    thread.start()

    return jsonify({"message": "Search started"})


@app.route("/api/location-preferences", methods=["GET"])
def api_get_location_prefs():
    return jsonify(LOCATION_PREFERENCES)


@app.route("/api/location-preferences", methods=["PUT"])
def api_update_location_prefs():
    data = request.get_json()
    if data:
        if "default_country" in data:
            LOCATION_PREFERENCES["default_country"] = data["default_country"]
        if "job_types" in data:
            LOCATION_PREFERENCES["job_types"] = data["job_types"]
        if "allowed_locations" in data:
            LOCATION_PREFERENCES["allowed_locations"] = data["allowed_locations"]
    return jsonify(LOCATION_PREFERENCES)


@app.route("/api/search/status", methods=["GET"])
def api_search_status():
    return jsonify(search_status)


# ---------------------------------------------------------------------------
# API: Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def api_get_stats():
    return jsonify(get_stats())


# ---------------------------------------------------------------------------
# Background search
# ---------------------------------------------------------------------------

def _run_search_background(params=None):
    global search_status
    search_status = {"running": True, "message": "Preparing search...", "progress": 10}

    try:
        if params is None:
            params = {}

        job_title = params.get("job_title", "")
        skills = params.get("skills", [])
        location = params.get("location", "remote")
        country = params.get("country", LOCATION_PREFERENCES.get("default_country", "India"))
        levels = params.get("levels", [])
        min_score = params.get("min_score", 0.3)
        min_salary = params.get("min_salary", 0)

        queries = []

        if job_title:
            queries.append(job_title)
            if location and location.lower() != "remote":
                queries.append(f"{job_title} {location}")

        if skills:
            for skill in skills[:5]:
                query = skill
                if levels:
                    query = f"{levels[0]} {skill} developer"
                queries.append(query)

            for i in range(0, min(len(skills), 6), 2):
                combo = " ".join(skills[i:i + 2])
                queries.append(combo)

        if not queries:
            queries = ["software engineer", "backend developer", "full stack developer"]

        queries = list(dict.fromkeys(queries))[:8]

        search_status["message"] = f"Searching for: {', '.join(queries[:3])}..."
        search_status["progress"] = 20

        all_jobs = search_all_boards(queries, location=location, country=country)

        # Filter by minimum salary if set
        if min_salary and min_salary > 0:
            import re as _re
            filtered = []
            for job in all_jobs:
                if not job.salary:
                    filtered.append(job)  # keep jobs without salary info
                    continue
                nums = _re.findall(r'[\d,]+', job.salary)
                if nums:
                    max_num = max(int(n.replace(',', '')) for n in nums)
                    if max_num >= min_salary:
                        filtered.append(job)
                else:
                    filtered.append(job)
            all_jobs = filtered

        search_status["message"] = f"Found {len(all_jobs)} jobs. Scoring..."
        search_status["progress"] = 60

        # Score all jobs (no filtering — save everything so the UI can filter)
        ranked = rank_jobs(all_jobs, min_score=0)
        matched_count = sum(
            1 for _, sd in ranked
            if sd["final_score"] >= min_score
        )

        search_status["message"] = f"Saving {len(ranked)} jobs..."
        search_status["progress"] = 80

        new_count = 0
        for job, score_data in ranked:
            if save_job(job, score_data):
                new_count += 1

        log_search_run(
            queries=queries,
            total_found=len(all_jobs),
            total_matched=matched_count,
            sources=[s.name for s in ALL_SCRAPERS],
        )

        search_status["message"] = f"Done! Found {len(all_jobs)} jobs, {matched_count} matched, {new_count} new."
        search_status["progress"] = 100

    except Exception as e:
        search_status["message"] = f"Error: {e}"
    finally:
        search_status["running"] = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = not os.environ.get("RENDER")  # disable debug on Render
    print("\n  Job Application Bot - API Server")
    print(f"  Running on port {port}")
    print("  API:      /api/")
    print("  Frontend: / (production build)\n")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
