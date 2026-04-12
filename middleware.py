"""Authentication middleware and profile helpers."""

import functools
import json
import os

from flask import jsonify, request, session

from tracker import get_user_by_id

_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAIL", "rajeshsinghkadyan@gmail.com").split(",")
    if e.strip()
}


def is_admin(user: dict) -> bool:
    return (user.get("email") or "").lower().strip() in _ADMIN_EMAILS


DEFAULT_PROFILE = {
    "name": "",
    "title": "",
    "email": "",
    "phone": "",
    "location": "",
    "years_of_experience": 0,
    "open_to": "Remote Roles",
    "summary": "",
    "skills": {},
    "experience": [],
    "education": "",
    "certifications": [],
    "linkedin_url": "",
    "github_url": "",
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


def _coerce_str(val) -> str:
    """Return a plain string from whatever the AI may have stored."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("name") or val.get("text") or val.get("value") or ""
    return str(val)


def _sanitize_profile(profile: dict) -> dict:
    """Coerce any profile field that the frontend renders as text to a plain string.
    Prevents React error #31 when AI parsers stored objects instead of strings."""
    # Top-level string fields
    for field in ("name", "title", "email", "phone", "location", "summary", "education",
                  "linkedin", "linkedin_url", "github", "github_url", "github_username",
                  "website", "notice_period"):
        if field in profile and not isinstance(profile[field], str):
            profile[field] = _coerce_str(profile[field])

    # skills: {category: [str, ...]}
    skills = profile.get("skills")
    if isinstance(skills, dict):
        for cat, vals in skills.items():
            if isinstance(vals, list):
                skills[cat] = [_coerce_str(v) for v in vals]

    # experience: [{title, company, period, highlights: [str]}]
    experience = profile.get("experience")
    if isinstance(experience, list):
        for exp in experience:
            if not isinstance(exp, dict):
                continue
            for f in ("title", "company", "period"):
                exp[f] = _coerce_str(exp.get(f, ""))
            exp["highlights"] = [_coerce_str(h) for h in (exp.get("highlights") or [])]

    # certifications: [str]
    certs = profile.get("certifications")
    if isinstance(certs, list):
        profile["certifications"] = [_coerce_str(c) for c in certs]

    # optimized_resume — sanitize recursively if present
    opt = profile.get("optimized_resume")
    if isinstance(opt, dict):
        if "summary" in opt:
            opt["summary"] = _coerce_str(opt["summary"])
        skills_opt = opt.get("skills") or {}
        if isinstance(skills_opt, dict):
            for cat, vals in skills_opt.items():
                if isinstance(vals, list):
                    skills_opt[cat] = [_coerce_str(v) for v in vals]
        for exp in (opt.get("experience") or []):
            if isinstance(exp, dict):
                for f in ("title", "company", "period"):
                    exp[f] = _coerce_str(exp.get(f, ""))
                exp["highlights"] = [_coerce_str(h) for h in (exp.get("highlights") or [])]
        for lst_field in ("ats_keywords", "optimization_notes", "certifications"):
            lst = opt.get(lst_field) or []
            if isinstance(lst, list):
                opt[lst_field] = [_coerce_str(v) for v in lst]

    return profile


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
    return _sanitize_profile(profile)
