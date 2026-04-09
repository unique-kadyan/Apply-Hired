"""Profile routes — view, update, resume upload, and avatar upload."""

import json
import logging
import os
import io
import base64

from flask import Blueprint, request, jsonify, current_app
from PIL import Image

from middleware import login_required, get_user_profile
from resume_parser import parse_resume, score_resume, _build_ai_providers, _call_ai_text, _is_quota_error, extract_text
from tracker import update_user_profile
from services.profile_import import import_github, import_linkedin_url, merge_github_into_profile

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__, url_prefix="/api/profile")


@profile_bp.route("", methods=["GET"])
@login_required
def get_profile():
    return jsonify(get_user_profile(request.user))


@profile_bp.route("", methods=["PUT", "POST"])
@login_required
def update_profile():
    data = request.get_json()
    profile = get_user_profile(request.user)
    if data:
        profile.update(data)
    update_user_profile(request.user["id"], profile)
    return jsonify(profile)


@profile_bp.route("/upload-resume", methods=["POST"])
@login_required
def upload_resume():
    if "resume" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not file.filename.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, file.filename)
    file.save(filepath)

    try:
        parsed = parse_resume(filepath)
        profile = get_user_profile(request.user)

        for key, value in parsed.items():
            if value:
                if isinstance(value, dict) and isinstance(profile.get(key), dict):
                    for k, v in value.items():
                        if v:
                            profile[key][k] = v
                else:
                    profile[key] = value

        # Score the resume
        try:
            resume_score = score_resume(filepath)
            print(f"[Resume Score] {resume_score.get('total_score', '?')}/100 via {resume_score.get('method', '?')}")
        except Exception as e:
            print(f"[Resume Score] FAILED: {e}")
            resume_score = None

        profile["resume_score"] = resume_score
        update_user_profile(request.user["id"], profile)
        return jsonify({"message": "Resume parsed successfully!", "profile": profile, "resume_score": resume_score})
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500


@profile_bp.route("/upload-avatar", methods=["POST"])
@login_required
def upload_avatar():
    """Resize and store profile picture as base64 in the user's profile."""
    if "avatar" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["avatar"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in allowed:
        return jsonify({"error": "Only JPG, PNG, WEBP, or GIF images are supported"}), 400

    try:
        img = Image.open(file.stream).convert("RGB")

        # Crop to square from centre, then resize to 200×200
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top  = (h - side) // 2
        img  = img.crop((left, top, left + side, top + side))
        img  = img.resize((200, 200), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64}"

        profile = get_user_profile(request.user)
        profile["avatar"] = data_uri
        update_user_profile(request.user["id"], profile)

        return jsonify({"avatar": data_uri, "profile": profile})
    except Exception as e:
        return jsonify({"error": f"Image processing failed: {str(e)}"}), 500


@profile_bp.route("/connect/github", methods=["POST"])
@login_required
def connect_github():
    data = request.get_json() or {}
    username = (data.get("username") or data.get("url") or "").strip()
    if not username:
        return jsonify({"error": "GitHub username or URL is required"}), 400

    # Use token from request body first, then fall back to stored profile token
    profile = get_user_profile(request.user)
    token = (data.get("token") or "").strip() or profile.get("github_token", "")

    # Save token to profile if provided (so it persists for future calls)
    if data.get("token", "").strip():
        profile["github_token"] = data["token"].strip()

    github_data = import_github(username, token=token)
    if github_data.get("error"):
        return jsonify({"error": github_data["error"], "rate_limit": "rate limit" in github_data["error"].lower()}), 400

    profile = merge_github_into_profile(profile, github_data)
    update_user_profile(request.user["id"], profile)

    stats = {
        "username": github_data.get("github_username"),
        "public_repos": github_data.get("public_repos", 0),
        "languages_added": len(github_data.get("languages", [])),
        "topics_added": len(github_data.get("topics", [])),
        "projects_added": len(github_data.get("top_repos", [])),
    }
    return jsonify({
        "message": f"GitHub imported: {stats['public_repos']} repos, {stats['languages_added']} languages, {stats['projects_added']} projects",
        "profile": profile,
        "stats": stats,
    })


@profile_bp.route("/connect/linkedin", methods=["POST"])
@login_required
def connect_linkedin():
    data = request.get_json() or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "LinkedIn URL is required"}), 400

    linkedin_data = import_linkedin_url(url)
    profile = get_user_profile(request.user)
    profile["linkedin"] = linkedin_data.get("linkedin_url", "")
    update_user_profile(request.user["id"], profile)

    return jsonify({"message": "LinkedIn connected!", "profile": profile})


@profile_bp.route("/connect/portfolio", methods=["POST"])
@login_required
def connect_portfolio():
    data = request.get_json() or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "Portfolio URL is required"}), 400

    profile = get_user_profile(request.user)
    profile["website"] = url.strip()
    update_user_profile(request.user["id"], profile)

    return jsonify({"message": "Portfolio connected!", "profile": profile})


@profile_bp.route("/autofill-data", methods=["GET"])
@login_required
def get_autofill_data():
    """Return profile data formatted for auto-filling job application forms.
    Used by the Chrome Extension."""
    profile = get_user_profile(request.user)
    name = profile.get("name", "")
    parts = name.split() if name else []

    skills_flat = ", ".join(
        s for group in (profile.get("skills") or {}).values() for s in group
    )

    return jsonify({
        "full_name": name,
        "first_name": parts[0] if parts else "",
        "last_name": parts[-1] if len(parts) > 1 else "",
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "location": profile.get("location", ""),
        "city": profile.get("location", "").split(",")[0].strip() if profile.get("location") else "",
        "title": profile.get("title", ""),
        "summary": profile.get("summary", ""),
        "years_of_experience": str(profile.get("years_of_experience", "")),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "website": profile.get("website", ""),
        "skills": skills_flat,
        "education": profile.get("education", ""),
        "cover_letter": "",  # filled per-job by the extension
        "notice_period": "Immediate / 15 days",
    })


_RESUME_JSON_SCHEMA = """{
  "personal": { "name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "website": "" },
  "title": "",
  "summary": "",
  "years_of_experience": 0,
  "notice_period": "",
  "expected_salary": { "min": null, "max": null, "currency": "", "period": "" },
  "skills": {
    "languages": [],
    "frameworks": [],
    "databases": [],
    "cloud_devops": [],
    "tools": []
  },
  "experience": [
    { "title": "", "company": "", "period": "", "highlights": [], "technologies": [] }
  ],
  "education": "",
  "certifications": [],
  "projects": [
    { "name": "", "description": "", "technologies": [], "url": "" }
  ],
  "achievements": []
}"""


@profile_bp.route("/parse-resume-json", methods=["POST"])
@login_required
def parse_resume_json():
    """Parse a resume into a standardised JSON schema using AI."""
    if "resume" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not file.filename.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, file.filename)
    file.save(filepath)

    try:
        text = extract_text(filepath)
        if not text or len(text.strip()) < 50:
            return jsonify({"error": "Could not extract text from resume"}), 400
    except Exception as e:
        return jsonify({"error": f"Text extraction failed: {str(e)}"}), 500

    prompt = f"""You are an expert resume parser. Extract all information from the resume below and return it as a single valid JSON object that strictly follows the schema provided.

RULES:
1. Return ONLY the JSON object — no markdown, no explanation, no ```json fences.
2. Keep ALL the exact keys from the schema — never rename or omit keys.
3. If a field is not found in the resume, use its default (empty string, 0, null, or empty array).
4. For 'skills': classify each skill into exactly one of: languages, frameworks, databases, cloud_devops, or tools.
5. For 'experience[].highlights': write complete sentences with metrics where available.
6. For 'years_of_experience': compute from dates in the resume (integer only).
7. For 'expected_salary': fill only if explicitly mentioned in the resume; otherwise leave defaults.
8. For 'notice_period': use exact text if stated, otherwise leave empty string.

TARGET JSON SCHEMA:
{_RESUME_JSON_SCHEMA}

RESUME TEXT:
{text[:6000]}
"""

    providers = _build_ai_providers()
    for provider in providers:
        try:
            result = _call_ai_text(provider, prompt)
            if not result:
                continue
            # Strip accidental markdown fences
            cleaned = result.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[-1] if cleaned.count("```") >= 2 else cleaned
                cleaned = cleaned.lstrip("json").strip().rstrip("`").strip()
            parsed = json.loads(cleaned)
            logger.info(f"Resume JSON parsed via {provider['name']}")
            return jsonify({"data": parsed})
        except (json.JSONDecodeError, Exception) as e:
            if _is_quota_error(e):
                continue
            logger.warning(f"parse-resume-json failed ({provider['name']}): {e}")
            continue

    return jsonify({"error": "AI parsing failed — all providers exhausted"}), 500


@profile_bp.route("/score-resume", methods=["POST"])
@login_required
def score_resume_endpoint():
    """Score a resume file without updating the profile."""
    if "resume" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not file.filename.lower().endswith((".pdf", ".docx", ".txt")):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, file.filename)
    file.save(filepath)

    try:
        result = score_resume(filepath)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Failed to score resume: {str(e)}"}), 500
