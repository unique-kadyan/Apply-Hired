"""Background scheduler — APScheduler-based periodic tasks.

Registered jobs:
  auto_search   — checks all users with auto_search_enabled every hour,
                  triggers a search when their chosen interval has elapsed.
  stale_pruner  — probes old job URLs for 404/410 once per week.
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def _keep_alive():
    """Ping own /health every 45 s to prevent Render free-tier spin-down."""
    url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not url:
        return
    try:
        import requests as _req
        r = _req.get(f"{url}/health", timeout=10)
        logger.debug(f"Keep-alive ping → {r.status_code}")
    except Exception as e:
        logger.warning(f"Keep-alive ping failed: {e}")

_scheduler = None

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
            last_run = user.get("auto_search_last_run")

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
                        continue

            if is_search_running(uid):
                continue

            params = user.get("auto_search_params") or {}
            start_search(params, uid)
            db.users.update_one({"_id": uid}, {"$set": {"auto_search_last_run": now}})
            logger.info(f"Auto-search triggered for user {uid}")

    except Exception as e:
        logger.error(f"Auto-search scheduler error: {e}")

def _run_stale_pruner():
    try:
        from services.stale_pruner import prune_stale_jobs
        prune_stale_jobs()
    except Exception as e:
        logger.error(f"Stale pruner error: {e}")

def start_scheduler():
    """Start the APScheduler BackgroundScheduler. Safe to call multiple times."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = BackgroundScheduler(daemon=True)

        _scheduler.add_job(
            _run_scheduled_searches,
            IntervalTrigger(hours=1),
            id="auto_search",
            replace_existing=True,
        )

        _scheduler.add_job(
            _run_stale_pruner,
            IntervalTrigger(hours=168),
            id="stale_pruner",
            replace_existing=True,
        )

        _scheduler.add_job(
            _keep_alive,
            IntervalTrigger(seconds=45),
            id="keep_alive",
            replace_existing=True,
        )

        _scheduler.start()
        logger.info("Background scheduler started (auto-search: hourly, stale-pruner: weekly, keep-alive: 45 s)")

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
