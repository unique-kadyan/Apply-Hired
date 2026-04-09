"""Background job search service."""

import re
import threading
from datetime import datetime, timedelta, timezone

from config import LOCATION_PREFERENCES, PROFILE, SEARCH_PREFERENCES
from matcher import rank_jobs
from scrapers import ALL_SCRAPERS, search_all_boards
from services.currency import normalize_salary_annual_usd
from tracker import (
    _PREDEFINED_REASONS,
    get_not_interested_reasons,
    log_search_run,
    save_jobs_bulk,
)

# Per-user search status keyed by user_id
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


def _run_search(params: dict, user_id: int):
    _status_map[user_id] = {"running": True, "message": "Preparing search...", "progress": 10}

    try:
        job_title = params.get("job_title", "")
        skills = params.get("skills", [])
        location = params.get("location", "remote")
        country = params.get("country", LOCATION_PREFERENCES.get("default_country", "India"))
        levels = params.get("levels", [])
        min_score = params.get("min_score", 0.3)
        min_salary = params.get("min_salary", 0)

        # Build targeted search queries
        queries = []
        level_prefix = levels[0] if levels else ""

        # 1. Explicit job title (with optional level prefix)
        if job_title:
            queries.append(job_title)
            if level_prefix:
                queries.append(f"{level_prefix} {job_title}")

        # 2. Skill-based queries
        if skills:
            for skill in skills[:4]:
                queries.append(f"{level_prefix} {skill} developer".strip() if level_prefix else f"{skill} developer")
            # Pair combinations (broader coverage)
            for i in range(0, min(len(skills), 6), 2):
                pair = " ".join(skills[i:i + 2])
                queries.append(pair)

        # 3. Profile-driven combination queries (framework + skill pairs)
        profile_backends = PROFILE.get("skills", {}).get("backend", [])[:2]
        if skills and profile_backends:
            queries.append(f"{skills[0]} {profile_backends[0]}")
        if level_prefix and profile_backends:
            queries.append(f"{level_prefix} {profile_backends[0]} developer")

        # 4. Target roles from SEARCH_PREFERENCES (adds breadth when no title given)
        if not job_title and not skills:
            for role in SEARCH_PREFERENCES.get("target_roles", [])[:3]:
                queries.append(role)

        if not queries:
            queries = ["software engineer", "backend developer", "full stack developer"]

        queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:10]

        _update(user_id, message=f"Searching for: {', '.join(queries[:3])}...", progress=20)

        all_jobs = search_all_boards(queries, location=location, country=country)

        # Post-scrape skill conflict filter:
        # Job boards do substring matching, so a "java" query returns javascript jobs.
        # For each skill that is a known prefix of another tech name, drop jobs whose
        # TITLE contains the conflicting tech but NOT the user's exact skill.
        #
        # Only applied when the user explicitly passed specific skills — not for
        # generic title-only searches where no skills were selected.
        if skills:
            # Map: user skill → list of longer tech names that contain it as a substring
            _CONFLICTS: dict[str, list[str]] = {
                "java":       ["javascript", "javafx"],
                "c":          ["c++", "c#", "objective-c", "cobol", "clojure"],
                "go":         ["golang"],   # "go" alone is ambiguous; golang is explicit
                "r":          ["ruby", "rust", "rails"],
                "python":     [],           # no common conflicts
                "kotlin":     [],
                "swift":      [],
                "rust":       ["rustic"],
                "perl":       ["perlite"],
                "dart":       [],
                "scala":      [],
                "spring":     [],
            }
            skill_set_lower = {s.lower() for s in skills}
            conflict_filters = []

            for skill in skill_set_lower:
                conflicts = _CONFLICTS.get(skill, [])
                # Find conflicting names that are NOT also in the user's skill set
                active_conflicts = [c for c in conflicts if c not in skill_set_lower]
                if active_conflicts:
                    conflict_filters.append((skill, active_conflicts))

            if conflict_filters:
                def _title_ok(job) -> bool:
                    title = job.title.lower()
                    for skill, conflicts in conflict_filters:
                        # Job title mentions a conflicting tech
                        for conflict in conflicts:
                            if re.search(rf"\b{re.escape(conflict)}\b", title):
                                # Allow only if the exact skill is also present as a standalone word
                                if not re.search(rf"\b{re.escape(skill)}\b", title):
                                    return False
                    return True

                before = len(all_jobs)
                all_jobs = [j for j in all_jobs if _title_ok(j)]
                dropped = before - len(all_jobs)
                if dropped:
                    _update(user_id, message=f"Filtered {dropped} mismatched skill jobs (e.g. JavaScript ≠ Java).")

        # Filter out jobs older than 4 months
        cutoff = datetime.now(timezone.utc) - timedelta(days=120)
        fresh = []
        for job in all_jobs:
            dp = job.date_posted or ""
            if not dp:
                fresh.append(job)  # no date → keep (can't tell)
                continue
            try:
                # Try ISO format first, then common date-only format
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
                    fresh.append(job)  # unparseable date → keep
            except Exception:
                fresh.append(job)
        all_jobs = fresh

        # Filter by minimum salary (min_salary is in USD, annual).
        # normalize_salary_annual_usd handles LPA, monthly, hourly, k-suffix, multi-currency.
        if min_salary and min_salary > 0:
            filtered = []
            for job in all_jobs:
                if not job.salary or not job.salary.strip():
                    continue  # skip jobs with no salary info
                annual_usd = normalize_salary_annual_usd(job.salary, job.location or "")
                if annual_usd is not None and annual_usd >= min_salary:
                    filtered.append(job)
            all_jobs = filtered

        # Filter out jobs that match topics the user has explicitly skipped.
        # Uses the full custom reason text (not tokenized keywords) matched against
        # job title + description. Predefined generic reasons are ignored.
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

        _update(user_id, message=f"Found {len(all_jobs)} jobs. Scoring...", progress=60)

        ranked = rank_jobs(all_jobs, min_score=0, selected_levels=levels or None)
        matched_count = sum(1 for _, sd in ranked if sd["final_score"] >= min_score)

        _update(user_id, message=f"Saving {len(ranked)} jobs...", progress=80)

        # Mark all existing "new" jobs as "previous" before saving fresh results
        from tracker import _get_db
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
