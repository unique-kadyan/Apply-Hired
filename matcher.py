"""Job matching and scoring engine — ranks jobs against resume profile."""

import logging
import re
from typing import Optional

from config import PROFILE, SEARCH_PREFERENCES
from constants import (
    AI_SCORE_WEIGHT,
    CITY_MATCH_BONUS,
    EXPERIENCE_LEVELS,
    JUNIOR_ROLE_PENALTY,
    LOCAL_SCORE_WEIGHT,
    OVERQUALIFIED_PENALTY_CAP,
    OVERQUALIFIED_PENALTY_PER_YEAR,
    REMOTE_LOCATION_BONUS,
    ROLE_TITLE_KEYWORDS,
    SENIOR_ROLE_BONUS,
    TITLE_EXACT_MATCH_BONUS,
    TITLE_KEYWORD_BONUS_CAP,
    TITLE_KEYWORD_BONUS_PER_MATCH,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword-based scoring (works without any API key)
# ---------------------------------------------------------------------------

def _flatten_skills() -> set[str]:
    """Flatten all profile skills into a lowercase set."""
    skills = set()
    for group in PROFILE["skills"].values():
        for s in group:
            skills.add(s.lower())
    return skills


def _keyword_score(job_title: str, job_description: str, job_tags: list[str]) -> float:
    """Score a job 0.0–1.0 based on keyword overlap with profile skills."""
    all_skills = _flatten_skills()
    text = f"{job_title} {job_description} {' '.join(job_tags)}".lower()

    matched = 0
    for skill in all_skills:
        # word-boundary match to avoid partial matches
        if re.search(rf"\b{re.escape(skill)}\b", text):
            matched += 1

    if not all_skills:
        return 0.0
    return matched / len(all_skills)


def _title_relevance(job_title: str) -> float:
    """Bonus score if the job title closely matches target roles."""
    title_lower = job_title.lower()
    for role in SEARCH_PREFERENCES["target_roles"]:
        if re.search(rf"\b{re.escape(role.lower())}\b", title_lower):
            return TITLE_EXACT_MATCH_BONUS
    matches = sum(1 for kw in ROLE_TITLE_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", title_lower))
    return min(matches * TITLE_KEYWORD_BONUS_PER_MATCH, TITLE_KEYWORD_BONUS_CAP)


LEVEL_YEAR_RANGES = EXPERIENCE_LEVELS  # alias — kept for any legacy callers


def _extract_required_years(text: str) -> int | None:
    """
    Parse the minimum years of experience a job requires.
    Looks for patterns like '8+ years', '10 years of experience', 'minimum 6 years'.
    Returns the highest number found (conservative: we want to avoid over-qualified filters).
    """
    patterns = [
        r'(\d+)\s*\+\s*years?',                    # 8+ years
        r'(\d+)\s*-\s*\d+\s*years?',               # 6-10 years → take first
        r'minimum\s+(\d+)\s+years?',               # minimum 8 years
        r'at\s+least\s+(\d+)\s+years?',            # at least 6 years
        r'(\d+)\s+years?\s+of\s+(?:relevant\s+)?(?:work\s+)?experience',
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            found.append(int(m.group(1)))
    return max(found) if found else None


def _seniority_check(job_title: str, job_description: str,
                     selected_levels: list[str] | None = None) -> float:
    """Penalize junior roles, reward senior-level matches.
    When selected_levels is given, also penalize jobs whose required years
    exceed the upper bound of all selected levels."""
    text = f"{job_title} {job_description}".lower()
    score = 0.0

    if any(word in text for word in ["junior", "entry level", "intern", "trainee", "graduate"]):
        score -= JUNIOR_ROLE_PENALTY
    elif any(word in text for word in ["senior", "lead", "staff", "principal", "sde-3", "sde 3", "iii"]):
        score += SENIOR_ROLE_BONUS

    # Year-based experience filter
    if selected_levels:
        max_years_allowed = None
        for lvl in selected_levels:
            rng = LEVEL_YEAR_RANGES.get(lvl)
            if rng:
                lvl_max = rng[1]  # None means no cap for this level
                if lvl_max is None:
                    max_years_allowed = None  # one level has no cap → no global cap
                    break
                if max_years_allowed is None:
                    max_years_allowed = lvl_max
                else:
                    max_years_allowed = max(max_years_allowed, lvl_max)

        if max_years_allowed is not None:
            required = _extract_required_years(text)
            if required is not None and required > max_years_allowed:
                # Penalty scales with how much over: +1 yr → -0.1, +3 yr → -0.25 (capped)
                excess = required - max_years_allowed
                score -= min(OVERQUALIFIED_PENALTY_PER_YEAR * excess, OVERQUALIFIED_PENALTY_CAP)

    return score


def _location_score(job_location: str) -> float:
    """Bonus score if the job location matches the user's city/country preference.

    Remote jobs always get +0.05 (broadly applicable).
    City/country match gives +0.10 (more targeted).
    """
    from config import LOCATION_PREFERENCES, PROFILE
    user_loc = PROFILE.get("location", "").lower()  # e.g. "rohtak, india"
    job_loc  = (job_location or "").lower()

    if not job_loc:
        return 0.0

    # Remote is always a positive signal
    if "remote" in job_loc or "worldwide" in job_loc or "anywhere" in job_loc:
        return REMOTE_LOCATION_BONUS

    user_tokens = [t.strip() for t in re.split(r"[,/]", user_loc) if len(t.strip()) > 2]
    for token in user_tokens:
        if token in job_loc:
            return CITY_MATCH_BONUS

    # Allowed locations from config
    for allowed in LOCATION_PREFERENCES.get("allowed_locations", []):
        if allowed.lower() in job_loc:
            return 0.08

    return 0.0


def score_job_local(job, selected_levels: list[str] | None = None) -> float:
    """Score a job using local keyword matching. Returns 0.0–1.0."""
    base = _keyword_score(job.title, job.description, job.tags)
    title_bonus = _title_relevance(job.title)
    seniority = _seniority_check(job.title, job.description, selected_levels)
    location_bonus = _location_score(job.location)
    return max(0.0, min(1.0, base + title_bonus + seniority + location_bonus))


# ---------------------------------------------------------------------------
# AI-powered scoring (requires OpenAI API key)
# ---------------------------------------------------------------------------

def score_job_ai(job) -> Optional[dict]:
    """Evaluate job fit using free AI providers with failover."""
    from resume_parser import (
        _build_ai_providers,
        _call_ai_text,
        _is_quota_error,
        _parse_ai_response,
    )

    providers = _build_ai_providers()
    if not providers:
        return None

    skills_text = ", ".join(
        skill for group in PROFILE["skills"].values() for skill in group
    )

    prompt = f"""Evaluate this job posting against the candidate profile below.
Return ONLY a JSON object with these fields:
- "score": float 0.0-1.0 (how well the candidate matches)
- "reasons": list of 3-5 short bullet points explaining the match
- "missing_skills": list of skills the job wants but the candidate lacks
- "recommendation": "strong_match" | "good_match" | "partial_match" | "weak_match"

IMPORTANT: Match skills precisely. "Java" and "JavaScript" are completely different technologies. A Java developer does NOT match a JavaScript role and vice versa. Score accordingly.

CANDIDATE:
- Title: {PROFILE['title']}
- Experience: {PROFILE['years_of_experience']} years
- Skills: {skills_text}
- Summary: {PROFILE['summary']}

JOB POSTING:
- Title: {job.title}
- Company: {job.company}
- Description: {job.description[:1000]}
- Tags: {', '.join(job.tags)}
"""

    for provider in providers:
        try:
            result_text = _call_ai_text(provider, prompt)
            parsed = _parse_ai_response(result_text)
            if parsed and "score" in parsed:
                return parsed
        except Exception as e:
            if _is_quota_error(e):
                continue
            logger.warning(f"AI scoring failed ({provider['name']}): {e}")
            continue

    return None


# ---------------------------------------------------------------------------
# Combined scorer
# ---------------------------------------------------------------------------

def score_job(job, use_ai: bool = False, selected_levels: list[str] | None = None) -> dict:
    """Score a job using local matching + optional AI. Returns scoring dict."""
    local_score = score_job_local(job, selected_levels)

    result = {
        "local_score": round(local_score, 3),
        "ai_score": None,
        "ai_reasons": [],
        "ai_missing_skills": [],
        "ai_recommendation": None,
        "final_score": round(local_score, 3),
    }

    # Only use AI scoring when explicitly requested (e.g. viewing job detail)
    if use_ai and local_score >= SEARCH_PREFERENCES["min_experience_match"]:
        ai_result = score_job_ai(job)
        if ai_result:
            result["ai_score"] = ai_result.get("score")
            result["ai_reasons"] = ai_result.get("reasons", [])
            result["ai_missing_skills"] = ai_result.get("missing_skills", [])
            result["ai_recommendation"] = ai_result.get("recommendation")
            if result["ai_score"] is not None:
                result["final_score"] = round(
                    LOCAL_SCORE_WEIGHT * local_score + AI_SCORE_WEIGHT * result["ai_score"], 3
                )

    return result


def rank_jobs(jobs: list, min_score: float | None = None,
              selected_levels: list[str] | None = None) -> list[tuple]:
    """Score and rank all jobs using fast local scoring only.

    AI scoring is skipped during bulk search for speed.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _score_one(job):
        return (job, score_job(job, use_ai=False, selected_levels=selected_levels))

    scored = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for job, score_data in executor.map(lambda j: _score_one(j), jobs):
            if min_score is not None and score_data["final_score"] < min_score:
                continue
            scored.append((job, score_data))

    scored.sort(key=lambda x: x[1]["final_score"], reverse=True)
    return scored
