"""Profile routes — view, update, and resume upload."""

import os

from flask import Blueprint, request, jsonify, current_app

from middleware import login_required, get_user_profile
from resume_parser import parse_resume
from tracker import update_user_profile

profile_bp = Blueprint("profile", __name__, url_prefix="/api/profile")


@profile_bp.route("", methods=["GET"])
@login_required
def get_profile():
    return jsonify(get_user_profile(request.user))


@profile_bp.route("", methods=["PUT"])
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

        update_user_profile(request.user["id"], profile)
        return jsonify({"message": "Resume parsed successfully!", "profile": profile})
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume: {str(e)}"}), 500
