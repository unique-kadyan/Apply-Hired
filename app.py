"""Flask REST API backend for Job Application Bot — with user auth."""

import os
import json
import random
import smtplib
import threading
import functools
import secrets
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode

import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory, session, redirect

from config import LOCATION_PREFERENCES
from scrapers import search_all_boards, ALL_SCRAPERS, Job
from matcher import rank_jobs
from cover_letter import generate_cover_letter
from resume_parser import parse_resume
from tracker import (
    init_db, save_job, get_jobs, get_stats, get_job_by_id,
    update_job_status, log_search_run,
    create_user, authenticate_user, get_user_by_id, update_user_profile,
)

app = Flask(__name__, static_folder="frontend/build", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Google OAuth config
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# SMTP config for sending OTP emails (use Gmail App Password)
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")      # e.g. your-gmail@gmail.com
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "") # Gmail App Password (16 chars)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))

# In-memory OTP store: { email: { "otp": "123456", "name": ..., "password": ..., "expires": timestamp } }
pending_otps: dict = {}

# In-memory state (per-user search status keyed by user_id)
search_status_map: dict[int, dict] = {}

# Default profile template for new users
DEFAULT_PROFILE = {
    "name": "", "title": "", "email": "", "phone": "", "location": "",
    "years_of_experience": 0, "open_to": "Remote Roles", "summary": "",
    "skills": {}, "experience": [], "education": "", "certifications": [],
}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    """Decorator to require authentication."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        user = get_user_by_id(user_id)
        if not user:
            session.clear()
            return jsonify({"error": "Authentication required"}), 401
        request.user = user
        return f(*args, **kwargs)
    return wrapper


def _get_user_profile(user) -> dict:
    """Parse the profile JSON from user record."""
    profile = user.get("profile", "{}")
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except (json.JSONDecodeError, TypeError):
            profile = {}
    if not profile:
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = user.get("name", "")
        profile["email"] = user.get("email", "")
    return profile


def _send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP verification email via SMTP."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"JobBot <{SMTP_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = f"JobBot — Your verification code is {otp}"

    html = f"""
    <div style="font-family:'Segoe UI',system-ui,sans-serif;max-width:480px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px">
        <h1 style="color:#60a5fa;margin:0 0 0.5rem">JobBot</h1>
        <p style="color:#94a3b8;margin:0 0 1.5rem">Verify your email to create your account</p>
        <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;
                    padding:1.5rem;text-align:center;margin-bottom:1.5rem">
            <p style="color:#94a3b8;margin:0 0 0.5rem;font-size:0.9rem">Your verification code</p>
            <div style="font-size:2.5rem;font-weight:800;letter-spacing:0.3em;color:#fff">{otp}</div>
        </div>
        <p style="color:#64748b;font-size:0.82rem;margin:0">
            This code expires in 10 minutes. If you didn't request this, ignore this email.
        </p>
    </div>
    """

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        import logging
        logging.error(f"Failed to send OTP email: {e}")
        return False


# ---------------------------------------------------------------------------
# Serve React app
# ---------------------------------------------------------------------------

@app.route("/")
def serve_react():
    return send_from_directory(app.static_folder, "index.html")

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# API: Auth
# ---------------------------------------------------------------------------

@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    """Step 1: Validate input and send OTP email."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if email already registered
    from tracker import _get_conn
    conn = _get_conn()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Send OTP email
    sent = _send_otp_email(email, otp)
    if not sent:
        return jsonify({"error": "Failed to send verification email. Check SMTP settings."}), 500

    # Store pending signup (expires in 10 minutes)
    pending_otps[email] = {
        "otp": otp,
        "name": name,
        "password": password,
        "expires": datetime.now().timestamp() + 600,
    }

    return jsonify({"message": "Verification code sent to your email", "needs_otp": True})


@app.route("/api/auth/verify-otp", methods=["POST"])
def api_verify_otp():
    """Step 2: Verify OTP and create account."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify({"error": "Email and verification code are required"}), 400

    pending = pending_otps.get(email)
    if not pending:
        return jsonify({"error": "No pending verification. Please sign up again."}), 400

    # Check expiry
    if datetime.now().timestamp() > pending["expires"]:
        del pending_otps[email]
        return jsonify({"error": "Verification code expired. Please sign up again."}), 400

    # Check OTP
    if otp != pending["otp"]:
        return jsonify({"error": "Invalid verification code"}), 400

    # OTP correct — create the account
    name = pending["name"]
    password = pending["password"]
    del pending_otps[email]

    user = create_user(name, email, password)
    if not user:
        return jsonify({"error": "An account with this email already exists"}), 409

    # Set initial profile
    profile = dict(DEFAULT_PROFILE)
    profile["name"] = name
    profile["email"] = email
    update_user_profile(user["id"], profile)

    session["user_id"] = user["id"]
    return jsonify({
        "message": "Account verified and created successfully",
        "user": {"id": user["id"], "name": name, "email": email},
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = authenticate_user(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    return jsonify({
        "message": "Logged in successfully",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
    })


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"user": None})
    return jsonify({
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
    })


# ---------------------------------------------------------------------------
# API: Google OAuth SSO
# ---------------------------------------------------------------------------

@app.route("/api/auth/google")
def google_login():
    """Redirect user to Google's OAuth consent screen."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."}), 500

    # Build the callback URL dynamically
    callback_url = request.url_root.rstrip("/") + "/api/auth/google/callback"
    if callback_url.startswith("http://") and "localhost" not in callback_url and "127.0.0.1" not in callback_url:
        callback_url = callback_url.replace("http://", "https://", 1)

    # Store a CSRF state token
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    })
    return redirect(f"{GOOGLE_AUTH_URL}?{params}")


@app.route("/api/auth/google/callback")
def google_callback():
    """Handle Google's OAuth callback — exchange code for tokens, create/login user."""
    error = request.args.get("error")
    if error:
        return redirect("/?auth_error=" + error)

    code = request.args.get("code")
    state = request.args.get("state")

    # Verify CSRF state
    if not state or state != session.pop("oauth_state", None):
        return redirect("/?auth_error=invalid_state")

    callback_url = request.url_root.rstrip("/") + "/api/auth/google/callback"
    if callback_url.startswith("http://") and "localhost" not in callback_url and "127.0.0.1" not in callback_url:
        callback_url = callback_url.replace("http://", "https://", 1)

    # Exchange authorization code for tokens
    try:
        token_resp = http_requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        }, timeout=10)
        token_data = token_resp.json()
    except Exception:
        return redirect("/?auth_error=token_exchange_failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return redirect("/?auth_error=no_access_token")

    # Fetch user info from Google
    try:
        user_resp = http_requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        google_user = user_resp.json()
    except Exception:
        return redirect("/?auth_error=userinfo_failed")

    email = google_user.get("email", "")
    name = google_user.get("name", email.split("@")[0])

    if not email:
        return redirect("/?auth_error=no_email")

    # Try to find existing user, or create a new one
    from tracker import _get_conn
    conn = _get_conn()
    row = conn.execute("SELECT id, name, email FROM users WHERE email = ?", (email.lower(),)).fetchone()

    if row:
        # Existing user — log them in
        user_id = row["id"]
    else:
        # New user — create account (random password since they use Google SSO)
        random_pw = secrets.token_urlsafe(32)
        user = create_user(name, email, random_pw)
        if not user:
            conn.close()
            return redirect("/?auth_error=account_creation_failed")
        user_id = user["id"]

        # Set initial profile
        profile = dict(DEFAULT_PROFILE)
        profile["name"] = name
        profile["email"] = email
        profile["picture"] = google_user.get("picture", "")
        update_user_profile(user_id, profile)

    conn.close()
    session["user_id"] = user_id

    # Redirect to the frontend — it will detect the session via /api/auth/me
    return redirect("/?auth_success=1")


# ---------------------------------------------------------------------------
# API: Profile (per-user)
# ---------------------------------------------------------------------------

@app.route("/api/profile", methods=["GET"])
@login_required
def api_get_profile():
    profile = _get_user_profile(request.user)
    return jsonify(profile)


@app.route("/api/profile", methods=["PUT"])
@login_required
def api_update_profile():
    data = request.get_json()
    profile = _get_user_profile(request.user)
    if data:
        profile.update(data)
    update_user_profile(request.user["id"], profile)
    return jsonify(profile)


@app.route("/api/profile/upload-resume", methods=["POST"])
@login_required
def api_upload_resume():
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
        profile = _get_user_profile(request.user)

        for key, value in parsed.items():
            if value:
                if isinstance(value, dict) and key in profile:
                    if isinstance(profile[key], dict):
                        for k, v in value.items():
                            if v:
                                profile[key][k] = v
                    else:
                        profile[key] = value
                else:
                    profile[key] = value

        update_user_profile(request.user["id"], profile)

        return jsonify({
            "message": "Resume parsed successfully!",
            "profile": profile,
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# API: Jobs (per-user)
# ---------------------------------------------------------------------------

@app.route("/api/jobs", methods=["GET"])
@login_required
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
        user_id=request.user["id"],
    )
    for job in jobs:
        job["tags"] = json.loads(job.get("tags", "[]"))
        job["score_details"] = json.loads(job.get("score_details", "{}"))

    return jsonify(jobs)


@app.route("/api/jobs/<int:job_id>", methods=["GET"])
@login_required
def api_get_job(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["tags"] = json.loads(job.get("tags", "[]"))
    job["score_details"] = json.loads(job.get("score_details", "{}"))
    return jsonify(job)


@app.route("/api/jobs/<int:job_id>/status", methods=["PUT"])
@login_required
def api_update_job_status(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.get_json()
    status = data.get("status", "new")
    notes = data.get("notes", "")
    update_job_status(job_id, status, notes)
    return jsonify({"message": f"Job #{job_id} updated to '{status}'"})


@app.route("/api/jobs/<int:job_id>/cover-letter", methods=["POST"])
@login_required
def api_generate_cover_letter(job_id):
    job = get_job_by_id(job_id, user_id=request.user["id"])
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
@login_required
def api_apply_jobs():
    data = request.get_json()
    job_ids = data.get("job_ids", [])

    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    results = []
    for job_id in job_ids:
        try:
            job = get_job_by_id(int(job_id), user_id=request.user["id"])
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
@login_required
def api_auto_apply():
    from auto_apply import auto_apply_batch

    data = request.get_json()
    job_ids = data.get("job_ids", [])

    if not job_ids:
        return jsonify({"error": "No jobs selected"}), 400
    if len(job_ids) > 10:
        return jsonify({"error": "Maximum 10 jobs at a time"}), 400

    jobs_with_letters = []
    for job_id in job_ids:
        try:
            job = get_job_by_id(int(job_id), user_id=request.user["id"])
            if not job:
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
                job["cover_letter"] = letter

            jobs_with_letters.append({
                "id": job["id"], "title": job["title"], "company": job["company"],
                "url": job["url"], "cover_letter": job.get("cover_letter", ""),
                "description": job.get("description", ""),
            })
        except Exception:
            continue

    results = auto_apply_batch(jobs_with_letters)

    for detail in results.get("details", []):
        if detail["status"] in ("opened", "auto_filled", "opened_browser"):
            update_job_status(
                detail["id"], "applied",
                f"Auto-applied on {datetime.now().strftime('%Y-%m-%d %H:%M')} ({detail['status']})"
            )

    return jsonify(results)


# ---------------------------------------------------------------------------
# API: Search (per-user)
# ---------------------------------------------------------------------------

@app.route("/api/search", methods=["POST"])
@login_required
def api_search():
    user_id = request.user["id"]
    user_status = search_status_map.get(user_id, {})
    if user_status.get("running"):
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

    thread = threading.Thread(
        target=_run_search_background,
        args=(search_params, user_id),
        daemon=True,
    )
    thread.start()

    return jsonify({"message": "Search started"})


@app.route("/api/location-preferences", methods=["GET"])
def api_get_location_prefs():
    return jsonify(LOCATION_PREFERENCES)


@app.route("/api/search/status", methods=["GET"])
@login_required
def api_search_status():
    user_id = request.user["id"]
    status = search_status_map.get(user_id, {"running": False, "message": "", "progress": 0})
    return jsonify(status)


# ---------------------------------------------------------------------------
# API: Stats (per-user)
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
@login_required
def api_get_stats():
    return jsonify(get_stats(user_id=request.user["id"]))


# ---------------------------------------------------------------------------
# Background search (per-user)
# ---------------------------------------------------------------------------

def _run_search_background(params=None, user_id=None):
    search_status_map[user_id] = {"running": True, "message": "Preparing search...", "progress": 10}

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

        search_status_map[user_id]["message"] = f"Searching for: {', '.join(queries[:3])}..."
        search_status_map[user_id]["progress"] = 20

        all_jobs = search_all_boards(queries, location=location, country=country)

        # Filter by minimum salary if set
        if min_salary and min_salary > 0:
            import re as _re
            filtered = []
            for job in all_jobs:
                if not job.salary:
                    filtered.append(job)
                    continue
                nums = _re.findall(r'[\d,]+', job.salary)
                if nums:
                    max_num = max(int(n.replace(',', '')) for n in nums)
                    if max_num >= min_salary:
                        filtered.append(job)
                else:
                    filtered.append(job)
            all_jobs = filtered

        search_status_map[user_id]["message"] = f"Found {len(all_jobs)} jobs. Scoring..."
        search_status_map[user_id]["progress"] = 60

        ranked = rank_jobs(all_jobs, min_score=0)
        matched_count = sum(
            1 for _, sd in ranked
            if sd["final_score"] >= min_score
        )

        search_status_map[user_id]["message"] = f"Saving {len(ranked)} jobs..."
        search_status_map[user_id]["progress"] = 80

        new_count = 0
        for job, score_data in ranked:
            if save_job(job, score_data, user_id=user_id):
                new_count += 1

        log_search_run(
            queries=queries,
            total_found=len(all_jobs),
            total_matched=matched_count,
            sources=[s.name for s in ALL_SCRAPERS],
            user_id=user_id,
        )

        search_status_map[user_id]["message"] = f"Done! Found {len(all_jobs)} jobs, {matched_count} matched, {new_count} new."
        search_status_map[user_id]["progress"] = 100

    except Exception as e:
        search_status_map[user_id]["message"] = f"Error: {e}"
    finally:
        search_status_map[user_id]["running"] = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = not os.environ.get("RENDER")
    print("\n  Job Application Bot - API Server")
    print(f"  Running on port {port}")
    print("  API:      /api/")
    print("  Frontend: / (production build)\n")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
