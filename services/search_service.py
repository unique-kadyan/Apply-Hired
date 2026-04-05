"""Background job search service."""

import re
import threading

from config import LOCATION_PREFERENCES
from scrapers import search_all_boards, ALL_SCRAPERS
from matcher import rank_jobs
from tracker import save_jobs_bulk, log_search_run

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

        # Build search queries
        queries = []
        if job_title:
            queries.append(job_title)
            if location and location.lower() != "remote":
                queries.append(f"{job_title} {location}")

        if skills:
            for skill in skills[:5]:
                query = f"{levels[0]} {skill} developer" if levels else skill
                queries.append(query)
            for i in range(0, min(len(skills), 6), 2):
                queries.append(" ".join(skills[i:i + 2]))

        if not queries:
            queries = ["software engineer", "backend developer", "full stack developer"]

        queries = list(dict.fromkeys(queries))[:8]

        _update(user_id, message=f"Searching for: {', '.join(queries[:3])}...", progress=20)

        all_jobs = search_all_boards(queries, location=location, country=country)

        # Filter by minimum salary
        if min_salary and min_salary > 0:
            filtered = []
            for job in all_jobs:
                if not job.salary:
                    filtered.append(job)
                    continue
                nums = re.findall(r'[\d,]+', job.salary)
                if nums:
                    max_num = max(int(n.replace(',', '')) for n in nums)
                    if max_num >= min_salary:
                        filtered.append(job)
                else:
                    filtered.append(job)
            all_jobs = filtered

        _update(user_id, message=f"Found {len(all_jobs)} jobs. Scoring...", progress=60)

        ranked = rank_jobs(all_jobs, min_score=0)
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
