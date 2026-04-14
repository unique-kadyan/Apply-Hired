"""Background job search service.

Resume-centric: each user's queries and ranking are derived from their actual
DB-stored profile (skills, title, years of experience), not from a global config.
The form params (job_title, skills, levels) are overrides — when omitted, the
search is seeded entirely from the user's resume.
"""

import logging
import re
import threading
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from config import LOCATION_PREFERENCES, PROFILE, SEARCH_PREFERENCES
from constants import JOB_MAX_AGE_DAYS, LANGUAGE_CONFLICTS, MAX_SEARCH_QUERIES
from matcher import rank_jobs
from middleware import get_user_profile
from scrapers import ALL_SCRAPERS, search_all_boards
from services.currency import normalize_salary_annual_usd
from services.events import publish
from tracker import (
    _PREDEFINED_REASONS,
    _get_db,
    get_not_interested_reasons,
    log_search_run,
    save_jobs_bulk,
)

logger = logging.getLogger(__name__)


def _load_user_profile(user_id) -> dict:
    """Fetch the per-user profile from MongoDB. Falls back to PROFILE on error."""
    try:
        db = _get_db()
        oid = ObjectId(str(user_id)) if not isinstance(user_id, ObjectId) else user_id
        user = db.users.find_one({"_id": oid}, {"profile": 1, "name": 1, "email": 1})
        if user:
            return get_user_profile(user)
    except Exception as e:
        logger.warning(f"Could not load user profile for {user_id}: {e} — using config fallback")
    return PROFILE


def _flatten_user_skills(user_profile: dict) -> list[str]:
    """Return user's skills as an ordered, de-duplicated list (preserves input order)."""
    out: list[str] = []
    seen: set[str] = set()
    src = user_profile.get("skills") or {}
    if isinstance(src, dict):
        for group_name in ("backend", "frontend", "languages", "databases", "cloud_devops",
                           "architecture", "testing", "other"):
            for s in (src.get(group_name) or []):
                if isinstance(s, str) and s.strip() and s.lower() not in seen:
                    seen.add(s.lower())
                    out.append(s.strip())
        # Catch any group not in the curated order
        for group_name, group in src.items():
            if group_name in ("backend", "frontend", "languages", "databases",
                              "cloud_devops", "architecture", "testing", "other"):
                continue
            for s in (group or []):
                if isinstance(s, str) and s.strip() and s.lower() not in seen:
                    seen.add(s.lower())
                    out.append(s.strip())
    elif isinstance(src, list):
        for s in src:
            if isinstance(s, str) and s.strip() and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s.strip())
    return out

_status_map: dict[int, dict] = {}

def get_search_status(user_id: int) -> dict:
    return _status_map.get(user_id, {"running": False, "message": "", "progress": 0})

def is_search_running(user_id: int) -> bool:
    return _status_map.get(user_id, {}).get("running", False)

def start_search(params: dict, user_id: int):
    """Launch a background search thread for a user."""
    thread = threading.Thread(
        target=_run_search,
        args=(params, user_id),
        daemon=True,
    )
    thread.start()

def _update(user_id: int, **kwargs):
    _status_map.setdefault(user_id, {}).update(kwargs)
    publish(str(user_id), "search_progress", _status_map[user_id])

def _run_search(params: dict, user_id: int):
    _status_map[user_id] = {"running": True, "message": "Preparing search...", "progress": 10}
    publish(str(user_id), "search_progress", _status_map[user_id])

    try:
        # Load this user's resume profile up front; everything below (queries, ranking,
        # scoring) is keyed off it so two different users never see the same ranked list.
        user_profile = _load_user_profile(user_id)
        user_skills = _flatten_user_skills(user_profile)
        user_title = (user_profile.get("title") or "").strip()
        user_target_roles = [r for r in (user_profile.get("target_roles") or []) if isinstance(r, str)]

        job_title = (params.get("job_title") or "").strip()
        form_skills = [s for s in (params.get("skills") or []) if isinstance(s, str) and s.strip()]
        location = params.get("location", "remote")
        country = params.get("country", LOCATION_PREFERENCES.get("default_country", "India"))
        levels = params.get("levels", [])
        min_score = params.get("min_score", 0.3)
        min_salary = params.get("min_salary", 0)

        # Form input takes precedence; otherwise seed from the user's actual resume.
        effective_skills = form_skills or user_skills[:8]
        effective_title = job_title or user_title

        queries: list[str] = []
        level_prefix = levels[0] if levels else ""

        if effective_title:
            queries.append(effective_title)
            if level_prefix:
                queries.append(f"{level_prefix} {effective_title}")

        # Title × top skill combos — these tend to be the highest-signal queries.
        for skill in effective_skills[:4]:
            if effective_title:
                queries.append(f"{effective_title} {skill}")
            queries.append(f"{level_prefix} {skill} developer".strip() if level_prefix else f"{skill} developer")

        # Skill pairs — "react node", "python aws", etc.
        for i in range(0, min(len(effective_skills), 8), 2):
            pair = " ".join(effective_skills[i:i + 2])
            if pair:
                queries.append(pair)

        # Target roles from the resume (e.g. "Senior Backend Engineer") — always seed these.
        for role in (user_target_roles or SEARCH_PREFERENCES.get("target_roles", []))[:3]:
            queries.append(role)

        if not queries:
            queries = ["software engineer", "backend developer", "full stack developer"]

        queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:MAX_SEARCH_QUERIES]
        # Re-bind for the rest of the function — keep variable names familiar below.
        skills = effective_skills

        _update(user_id, message=f"Searching for: {', '.join(queries[:3])}...", progress=20)

        all_jobs = search_all_boards(queries, location=location, country=country)

        if skills:
            skill_set_lower = {s.lower() for s in skills}
            conflict_filters = []

            for skill in skill_set_lower:
                conflicts = LANGUAGE_CONFLICTS.get(skill, [])
                active_conflicts = [c for c in conflicts if c not in skill_set_lower]
                if active_conflicts:
                    conflict_filters.append((skill, active_conflicts))

            if conflict_filters:
                def _title_ok(job) -> bool:
                    title = job.title.lower()
                    for skill, conflicts in conflict_filters:
                        for conflict in conflicts:
                            if re.search(rf"\b{re.escape(conflict)}\b", title):
                                if not re.search(rf"\b{re.escape(skill)}\b", title):
                                    return False
                    return True

                before = len(all_jobs)
                all_jobs = [j for j in all_jobs if _title_ok(j)]
                dropped = before - len(all_jobs)
                if dropped:
                    _update(user_id, message=f"Filtered {dropped} mismatched skill jobs (e.g. JavaScript ≠ Java).")

        cutoff = datetime.now(timezone.utc) - timedelta(days=JOB_MAX_AGE_DAYS)
        fresh = []
        for job in all_jobs:
            dp = job.date_posted or ""
            if not dp:
                fresh.append(job)
                continue
            try:
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(dp[:19], fmt[:len(dp[:19])])
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt >= cutoff:
                            fresh.append(job)
                        break
                    except ValueError:
                        continue
                else:
                    fresh.append(job)
            except Exception:
                fresh.append(job)
        all_jobs = fresh

        if min_salary and min_salary > 0:
            filtered = []
            for job in all_jobs:
                if not job.salary or not job.salary.strip():
                    continue
                annual_usd = normalize_salary_annual_usd(job.salary, job.location or "")
                if annual_usd is not None and annual_usd >= min_salary:
                    filtered.append(job)
            all_jobs = filtered

        custom_reasons = [
            r for r in get_not_interested_reasons(user_id)
            if r not in _PREDEFINED_REASONS
        ]
        if custom_reasons:
            skip_patterns = [re.compile(re.escape(r), re.IGNORECASE) for r in custom_reasons]
            before = len(all_jobs)
            all_jobs = [
                job for job in all_jobs
                if not any(
                    p.search(job.title) or p.search(job.description or "")
                    for p in skip_patterns
                )
            ]
            skipped = before - len(all_jobs)
            if skipped:
                _update(user_id, message=f"Filtered {skipped} jobs matching your skip topics.")

        _update(user_id, message=f"Found {len(all_jobs)} jobs. Scoring against your resume...", progress=60)

        ranked = rank_jobs(
            all_jobs,
            min_score=min_score,
            selected_levels=levels or None,
            user_profile=user_profile,
        )
        matched_count = len(ranked)

        _update(user_id, message=f"Saving {len(ranked)} matched jobs...", progress=80)

        db = _get_db()
        db.jobs.update_many(
            {"user_id": str(user_id), "status": "fresh new"},
            {"$set": {"status": "new"}},
        )

        new_count = save_jobs_bulk(ranked, user_id=user_id)

        log_search_run(
            queries=queries,
            total_found=len(all_jobs),
            total_matched=matched_count,
            sources=[s.name for s in ALL_SCRAPERS],
            user_id=user_id,
        )

        _update(user_id,
                message=f"Done! Found {len(all_jobs)} jobs, {matched_count} matched, {new_count} new.",
                progress=100)

    except Exception as e:
        _update(user_id, message=f"Error: {e}")
    finally:
        _status_map[user_id]["running"] = False
        publish(str(user_id), "search_progress", _status_map[user_id])
        publish(str(user_id), "jobs_changed", {"reason": "search_completed"})
