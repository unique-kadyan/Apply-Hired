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

def _flatten_skills(user_profile: Optional[dict] = None) -> set[str]:
    """Flatten all profile skills into a lowercase set.

    If user_profile is provided, use its skills (per-user resume-centric matching).
    Otherwise fall back to the static config.PROFILE — kept for any caller that
    hasn't been migrated to pass the per-user profile.
    """
    src = (user_profile or PROFILE).get("skills") or {}
    skills: set[str] = set()
    if isinstance(src, dict):
        for group in src.values():
            if isinstance(group, list):
                for s in group:
                    if isinstance(s, str) and s.strip():
                        skills.add(s.lower().strip())
    elif isinstance(src, list):
        for s in src:
            if isinstance(s, str) and s.strip():
                skills.add(s.lower().strip())
    return skills


def _keyword_score(
    job_title: str,
    job_description: str,
    job_tags: list[str],
    user_profile: Optional[dict] = None,
) -> float:
    """Score a job 0.0–1.0 based on keyword overlap with the user's skills."""
    all_skills = _flatten_skills(user_profile)
    text = f"{job_title} {job_description} {' '.join(job_tags)}".lower()

    matched = 0
    for skill in all_skills:
        if re.search(rf"\b{re.escape(skill)}\b", text):
            matched += 1

    if not all_skills:
        return 0.0
    return matched / len(all_skills)


def _title_relevance(job_title: str, user_profile: Optional[dict] = None) -> float:
    """Bonus score if the job title closely matches the user's target role(s)."""
    title_lower = job_title.lower()
    target_roles: list[str] = []
    if user_profile:
        if user_profile.get("title"):
            target_roles.append(str(user_profile["title"]))
        for r in (user_profile.get("target_roles") or []):
            if isinstance(r, str) and r.strip():
                target_roles.append(r)
    if not target_roles:
        target_roles = list(SEARCH_PREFERENCES["target_roles"])

    for role in target_roles:
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
                     selected_levels: list[str] | None = None,
                     user_profile: Optional[dict] = None) -> float:
    """Penalize junior roles, reward senior-level matches.
    When selected_levels is given, also penalize jobs whose required years
    exceed the upper bound of all selected levels.
    When user_profile is given, also penalize jobs whose required years
    significantly exceed the user's actual experience."""
    text = f"{job_title} {job_description}".lower()
    score = 0.0

    if any(word in text for word in ["junior", "entry level", "intern", "trainee", "graduate"]):
        score -= JUNIOR_ROLE_PENALTY
    elif any(word in text for word in ["senior", "lead", "staff", "principal", "sde-3", "sde 3", "iii"]):
        score += SENIOR_ROLE_BONUS

    # Year-based experience filter (form-selected levels)
    required = _extract_required_years(text)
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

        if max_years_allowed is not None and required is not None and required > max_years_allowed:
            excess = required - max_years_allowed
            score -= min(OVERQUALIFIED_PENALTY_PER_YEAR * excess, OVERQUALIFIED_PENALTY_CAP)

    # Resume-centric: penalise jobs requiring far more years than the user has.
    # Soft penalty so a 6.8-yr user still sees 8-yr roles, but a 10-yr "lead/staff"
    # role won't be #1 if the user is mid-level.
    if user_profile and required is not None:
        try:
            user_years = float(user_profile.get("years_of_experience") or 0)
        except (TypeError, ValueError):
            user_years = 0.0
        # Allow 2 years' stretch beyond what the user has.
        gap = required - user_years - 2
        if gap > 0:
            score -= min(OVERQUALIFIED_PENALTY_PER_YEAR * gap, OVERQUALIFIED_PENALTY_CAP)

    return score


def _location_score(job_location: str, user_profile: Optional[dict] = None) -> float:
    """Bonus score if the job location matches the user's city/country preference."""
    from config import LOCATION_PREFERENCES, PROFILE
    src = user_profile or PROFILE
    user_loc = (src.get("location") or "").lower()
    job_loc  = (job_location or "").lower()

    if not job_loc:
        return 0.0

    if "remote" in job_loc or "worldwide" in job_loc or "anywhere" in job_loc:
        return REMOTE_LOCATION_BONUS

    user_tokens = [t.strip() for t in re.split(r"[,/]", user_loc) if len(t.strip()) > 2]
    for token in user_tokens:
        if token in job_loc:
            return CITY_MATCH_BONUS

    for allowed in LOCATION_PREFERENCES.get("allowed_locations", []):
        if allowed.lower() in job_loc:
            return 0.08

    return 0.0


def score_job_local(
    job,
    selected_levels: list[str] | None = None,
    user_profile: Optional[dict] = None,
) -> float:
    """Score a job using keyword matching against the user's resume profile.
    Returns 0.0–1.0. Falls back to config.PROFILE if user_profile is None."""
    base = _keyword_score(job.title, job.description, job.tags, user_profile)
    title_bonus = _title_relevance(job.title, user_profile)
    seniority = _seniority_check(job.title, job.description, selected_levels, user_profile)
    location_bonus = _location_score(job.location, user_profile)
    return max(0.0, min(1.0, base + title_bonus + seniority + location_bonus))


# ---------------------------------------------------------------------------
# AI-powered scoring (requires OpenAI API key)
# ---------------------------------------------------------------------------

def score_job_ai(job, user_profile: Optional[dict] = None) -> Optional[dict]:
    """Evaluate job fit using free AI providers with failover.
    Uses user_profile if provided, else falls back to config.PROFILE."""
    from resume_parser import (
        _build_ai_providers,
        _call_ai_text,
        _is_quota_error,
        _parse_ai_response,
    )

    providers = _build_ai_providers()
    if not providers:
        return None

    src = user_profile or PROFILE
    src_skills = src.get("skills") or {}
    if isinstance(src_skills, dict):
        skills_text = ", ".join(
            s for group in src_skills.values() if isinstance(group, list)
            for s in group if isinstance(s, str)
        )
    elif isinstance(src_skills, list):
        skills_text = ", ".join(s for s in src_skills if isinstance(s, str))
    else:
        skills_text = ""

    prompt = f"""Evaluate this job posting against the candidate profile below.
Return ONLY a JSON object with these fields:
- "score": float 0.0-1.0 (how well the candidate matches)
- "reasons": list of 3-5 short bullet points explaining the match
- "missing_skills": list of skills the job wants but the candidate lacks
- "recommendation": "strong_match" | "good_match" | "partial_match" | "weak_match"

IMPORTANT: Match skills precisely. "Java" and "JavaScript" are completely different technologies. A Java developer does NOT match a JavaScript role and vice versa. Score accordingly.

CANDIDATE:
- Title: {src.get('title', '')}
- Experience: {src.get('years_of_experience', '')} years
- Skills: {skills_text}
- Summary: {src.get('summary', '')}

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

def score_job(
    job,
    use_ai: bool = False,
    selected_levels: list[str] | None = None,
    user_profile: Optional[dict] = None,
) -> dict:
    """Score a job using local matching + optional AI. Returns scoring dict."""
    local_score = score_job_local(job, selected_levels, user_profile)

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
        ai_result = score_job_ai(job, user_profile)
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


def rank_jobs(
    jobs: list,
    min_score: float | None = None,
    selected_levels: list[str] | None = None,
    user_profile: Optional[dict] = None,
) -> list[tuple]:
    """Score and rank all jobs against the user's resume profile.

    AI scoring is skipped during bulk search for speed.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _score_one(job):
        return (
            job,
            score_job(job, use_ai=False, selected_levels=selected_levels, user_profile=user_profile),
        )

    scored = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for job, score_data in executor.map(lambda j: _score_one(j), jobs):
            if min_score is not None and score_data["final_score"] < min_score:
                continue
            scored.append((job, score_data))

    scored.sort(key=lambda x: x[1]["final_score"], reverse=True)
    return scored
