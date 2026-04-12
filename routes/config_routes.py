"""Public config endpoint — exposes non-sensitive constants to the frontend."""

from flask import Blueprint, jsonify

from constants import (
    COUNTRY_OPTIONS,
    DAILY_ACTIVITY_DAYS,
    DEFAULT_SCHEDULE_INTERVAL_HOURS,
    EXPERIENCE_LEVEL_LABELS,
    EXPERIENCE_LEVELS,
    SALARY_LABEL_BREAKPOINTS,
    SALARY_MAX_USD,
    SALARY_MIN_USD,
    SALARY_STEP_USD,
    SCHEDULE_INTERVAL_OPTIONS,
    SCHEDULE_REFRESH_INTERVAL_MS,
    SEARCH_POLL_INTERVAL_MS,
)
from services.currency import USD_RATES

config_bp = Blueprint("config", __name__, url_prefix="/api/config")


@config_bp.route("", methods=["GET"])
def get_config():
    """Return all frontend-relevant configuration values.
    No authentication required — contains only non-sensitive UI constants."""
    experience_levels = [
        {
            "value": level,
            "label": level,
            "years": EXPERIENCE_LEVEL_LABELS[level],
            "min_years": rng[0],
            "max_years": rng[1],
        }
        for level, rng in EXPERIENCE_LEVELS.items()
    ]
    return jsonify({
        "experience_levels": experience_levels,
        "schedule_interval_options": SCHEDULE_INTERVAL_OPTIONS,
        "default_schedule_interval_hours": DEFAULT_SCHEDULE_INTERVAL_HOURS,
        "country_options": COUNTRY_OPTIONS,
        "salary": {
            "min_usd": SALARY_MIN_USD,
            "max_usd": SALARY_MAX_USD,
            "step_usd": SALARY_STEP_USD,
            "label_breakpoints": SALARY_LABEL_BREAKPOINTS,
        },
        "poll_intervals": {
            "search_status_ms": SEARCH_POLL_INTERVAL_MS,
            "schedule_refresh_ms": SCHEDULE_REFRESH_INTERVAL_MS,
        },
        "stats": {
            "daily_activity_days": DAILY_ACTIVITY_DAYS,
        },
        "exchange_rates": {k: v for k, v in USD_RATES.items()},
    })
