"""Authentication middleware and profile helpers."""

import json
import functools

from flask import request, jsonify, session

from tracker import get_user_by_id

DEFAULT_PROFILE = {
    "name": "", "title": "", "email": "", "phone": "", "location": "",
    "years_of_experience": 0, "open_to": "Remote Roles", "summary": "",
    "skills": {}, "experience": [], "education": "", "certifications": [],
}


def login_required(f):
    """Decorator — rejects unauthenticated requests with 401."""
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


def get_user_profile(user: dict) -> dict:
    """Parse the profile JSON stored on a user record."""
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
