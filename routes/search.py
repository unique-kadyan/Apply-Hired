"""Search & stats routes."""

from flask import Blueprint, jsonify, request

from config import LOCATION_PREFERENCES
from middleware import get_user_profile, login_required
from services.search_service import get_search_status, is_search_running, start_search
from services.tier import get_user_tier
from tracker import _get_db, _to_object_id, get_stats

_CURRENCY_TO_USD = {
    "INR": 83.5, "EUR": 0.92, "GBP": 0.79, "AED": 3.67,
    "SGD": 1.35, "USD": 1.0,
}

def _expected_salary_usd(profile: dict) -> float:
    """Convert profile expected salary (min) to annual USD for search filtering."""
    sal_min = profile.get("expected_salary_min")
    if not sal_min:
        return 0.0
    currency = profile.get("expected_salary_currency", "USD")
    period = profile.get("expected_salary_period", "annually")
    rate = _CURRENCY_TO_USD.get(currency.upper(), 1.0)
    annual = float(sal_min) * (12 if period == "monthly" else 1)
    return annual / rate

search_bp = Blueprint("search", __name__, url_prefix="/api")

@search_bp.route("/search", methods=["POST"])
@login_required
def run_search():
    user_id = request.user["id"]
    if is_search_running(user_id):
        return jsonify({"error": "A search is already running"}), 409

    data = request.get_json() or {}

    profile = get_user_profile(request.user)
    default_min_salary = _expected_salary_usd(profile)

    params = {
        "job_title": data.get("job_title", ""),
        "skills": data.get("skills", []),
        "location": data.get("location", "remote"),
        "country": data.get("country", LOCATION_PREFERENCES.get("default_country", "India")),
        "levels": data.get("levels", []),
        "min_score": data.get("min_score", 0.3),
        "min_salary": data.get("min_salary") if data.get("min_salary") is not None else default_min_salary,
    }
    start_search(params, user_id)
    return jsonify({"message": "Search started"})

@search_bp.route("/search/status", methods=["GET"])
@login_required
def search_status():
    return jsonify(get_search_status(request.user["id"]))

@search_bp.route("/location-preferences", methods=["GET"])
def location_prefs():
    return jsonify(LOCATION_PREFERENCES)

@search_bp.route("/stats", methods=["GET"])
@login_required
def stats():
    return jsonify(get_stats(user_id=request.user["id"]))

@search_bp.route("/search/schedule", methods=["GET"])
@login_required
def get_schedule():
    """Return this user's auto-search schedule settings."""
    db = _get_db()
    user = db.users.find_one(
        {"_id": _to_object_id(request.user["id"])},
        {"auto_search_enabled": 1, "auto_search_interval_hours": 1,
         "auto_search_params": 1, "auto_search_last_run": 1},
    )
    last_run = user.get("auto_search_last_run") if user else None
    if hasattr(last_run, "isoformat"):
        last_run = last_run.isoformat()
    return jsonify({
        "enabled": bool((user or {}).get("auto_search_enabled", False)),
        "interval_hours": (user or {}).get("auto_search_interval_hours", 24),
        "last_run": last_run,
        "params": (user or {}).get("auto_search_params", {}),
    })

@search_bp.route("/search/schedule", methods=["PUT"])
@login_required
def set_schedule():
    """Save auto-search schedule settings for this user.
    Auto-search is a Pro feature — free users cannot enable it."""
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", False))
    tier = get_user_tier(request.user)
    if enabled and tier not in ("admin", "pro"):
        return jsonify({
            "error": "Auto-search is a Pro feature.",
            "message": "Upgrade to Pro to schedule recurring job searches every hour.",
            "tier": tier,
        }), 402
    db = _get_db()
    db.users.update_one(
        {"_id": _to_object_id(request.user["id"])},
        {"$set": {
            "auto_search_enabled": enabled,
            "auto_search_interval_hours": int(data.get("interval_hours", 24)),
            "auto_search_params": data.get("params", {}),
        }},
    )
    return jsonify({"message": "Schedule saved"})
