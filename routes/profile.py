"""Profile routes — view, update, resume upload, and avatar upload."""

import os
import io
import base64

from flask import Blueprint, request, jsonify, current_app
from PIL import Image

from middleware import login_required, get_user_profile
from resume_parser import parse_resume, score_resume
from tracker import update_user_profile
from services.profile_import import import_github, import_linkedin_url, merge_github_into_profile

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

    github_data = import_github(username)
    if github_data.get("error"):
        return jsonify({"error": github_data["error"]}), 400

    profile = get_user_profile(request.user)
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
