"""Background scheduler — APScheduler-based periodic tasks.

Registered jobs:
  auto_search   — checks all users with auto_search_enabled every hour,
                  triggers a search when their chosen interval has elapsed.
  stale_pruner  — probes old job URLs for 404/410 once per week.
  keep_alive    — pings /health every 25 seconds to prevent Render free-tier
                  instance suspension (threshold: ~40 s of inactivity).
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keep-alive ping (Render free tier)
# ---------------------------------------------------------------------------

def _keep_alive():
    """Self-ping /health so Render never sees 40 s of inactivity."""
    app_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL", "")
    if not app_url:
        return  # local dev — skip
    try:
        import urllib.request
        url = app_url.rstrip("/") + "/health"
        with urllib.request.urlopen(url, timeout=10) as resp:  # nosec B310
            logger.debug(f"Keep-alive ping → {resp.status}")
    except Exception as e:
        logger.debug(f"Keep-alive ping failed (non-critical): {e}")

_scheduler = None  # BackgroundScheduler instance (initialised lazily)


# ---------------------------------------------------------------------------
# Auto-search runner
# ---------------------------------------------------------------------------

def _run_scheduled_searches():
    """Called every hour. Triggers searches for users whose interval has elapsed."""
    try:
        from services.search_service import is_search_running, start_search
        from tracker import _get_db

        db = _get_db()
        now = datetime.now(timezone.utc)

        users = list(db.users.find(
            {"auto_search_enabled": True},
            {"_id": 1, "auto_search_params": 1,
             "auto_search_interval_hours": 1, "auto_search_last_run": 1},
        ))

        for user in users:
            uid = user["_id"]
            interval_h = float(user.get("auto_search_interval_hours") or 24)
            last_run = user.get("auto_search_last_run")  # datetime or None

            if last_run:
                if isinstance(last_run, str):
                    try:
                        last_run = datetime.fromisoformat(last_run)
                    except ValueError:
                        last_run = None
                if last_run:
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    elapsed_h = (now - last_run).total_seconds() / 3600
                    if elapsed_h < interval_h:
                        continue  # not yet time

            if is_search_running(uid):
                continue  # already running for this user

            params = user.get("auto_search_params") or {}
            start_search(params, uid)
            db.users.update_one({"_id": uid}, {"$set": {"auto_search_last_run": now}})
            logger.info(f"Auto-search triggered for user {uid}")

    except Exception as e:
        logger.error(f"Auto-search scheduler error: {e}")


# ---------------------------------------------------------------------------
# Stale pruner runner
# ---------------------------------------------------------------------------

def _run_stale_pruner():
    try:
        from services.stale_pruner import prune_stale_jobs
        prune_stale_jobs()
    except Exception as e:
        logger.error(f"Stale pruner error: {e}")


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start_scheduler():
    """Start the APScheduler BackgroundScheduler. Safe to call multiple times."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = BackgroundScheduler(daemon=True)

        # Check auto-search eligibility every hour
        _scheduler.add_job(
            _run_scheduled_searches,
            IntervalTrigger(hours=1),
            id="auto_search",
            replace_existing=True,
        )

        # Probe stale job URLs once per week (168 hours)
        _scheduler.add_job(
            _run_stale_pruner,
            IntervalTrigger(hours=168),
            id="stale_pruner",
            replace_existing=True,
        )

        # Keep-alive: ping /health every 25 s (Render free tier suspends at ~40 s inactivity)
        # Only active when RENDER_EXTERNAL_URL or APP_URL env var is set.
        if os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL"):
            _scheduler.add_job(
                _keep_alive,
                IntervalTrigger(seconds=25),
                id="keep_alive",
                replace_existing=True,
            )
            logger.info("Keep-alive ping registered (every 25 s)")

        _scheduler.start()
        logger.info("Background scheduler started (auto-search: hourly, stale-pruner: weekly)")

    except ImportError:
        logger.warning("APScheduler not installed — scheduled tasks disabled. Run: pip install APScheduler")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")


def stop_scheduler():
    """Gracefully stop the scheduler (called on app teardown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
