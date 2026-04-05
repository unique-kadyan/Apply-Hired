"""Search & stats routes."""

from flask import Blueprint, request, jsonify

from config import LOCATION_PREFERENCES
from middleware import login_required
from services.search_service import get_search_status, is_search_running, start_search
from tracker import get_stats

search_bp = Blueprint("search", __name__, url_prefix="/api")


@search_bp.route("/search", methods=["POST"])
@login_required
def run_search():
    user_id = request.user["id"]
    if is_search_running(user_id):
        return jsonify({"error": "A search is already running"}), 409

    data = request.get_json() or {}
    params = {
        "job_title": data.get("job_title", ""),
        "skills": data.get("skills", []),
        "location": data.get("location", "remote"),
        "country": data.get("country", LOCATION_PREFERENCES.get("default_country", "India")),
        "levels": data.get("levels", []),
        "min_score": data.get("min_score", 0.3),
        "min_salary": data.get("min_salary", 0),
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
