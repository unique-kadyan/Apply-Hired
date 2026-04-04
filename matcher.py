"""Job matching and scoring engine — ranks jobs against resume profile."""

import re
import logging
from typing import Optional

from config import PROFILE, SEARCH_PREFERENCES, OPENAI_API_KEY

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
        if role.lower() in title_lower or title_lower in role.lower():
            return 0.2
    # Partial matches
    role_keywords = {"senior", "backend", "engineer", "developer", "java", "python", "spring", "full stack", "sde", "platform"}
    matches = sum(1 for kw in role_keywords if kw in title_lower)
    return min(matches * 0.05, 0.15)


def _seniority_check(job_title: str, job_description: str) -> float:
    """Penalize junior roles, reward senior-level matches."""
    text = f"{job_title} {job_description}".lower()
    if any(word in text for word in ["junior", "entry level", "intern", "trainee", "graduate"]):
        return -0.3
    if any(word in text for word in ["senior", "lead", "staff", "principal", "sde-3", "sde 3", "iii"]):
        return 0.1
    return 0.0


def score_job_local(job) -> float:
    """Score a job using local keyword matching. Returns 0.0–1.0."""
    base = _keyword_score(job.title, job.description, job.tags)
    title_bonus = _title_relevance(job.title)
    seniority = _seniority_check(job.title, job.description)
    return max(0.0, min(1.0, base + title_bonus + seniority))


# ---------------------------------------------------------------------------
# AI-powered scoring (requires OpenAI API key)
# ---------------------------------------------------------------------------

def score_job_ai(job) -> Optional[dict]:
    """Use OpenAI GPT to deeply evaluate job fit. Returns dict with score + reasoning."""
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — skipping AI scoring")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    skills_text = ", ".join(
        skill for group in PROFILE["skills"].values() for skill in group
    )

    prompt = f"""Evaluate this job posting against the candidate profile below.
Return ONLY a JSON object with these fields:
- "score": float 0.0-1.0 (how well the candidate matches)
- "reasons": list of 3-5 short bullet points explaining the match
- "missing_skills": list of skills the job wants but the candidate lacks
- "recommendation": "strong_match" | "good_match" | "partial_match" | "weak_match"

CANDIDATE:
- Title: {PROFILE['title']}
- Experience: {PROFILE['years_of_experience']} years
- Skills: {skills_text}
- Summary: {PROFILE['summary']}

JOB POSTING:
- Title: {job.title}
- Company: {job.company}
- Description: {job.description[:2000]}
- Tags: {', '.join(job.tags)}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.choices[0].message.content
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logger.warning(f"AI scoring failed: {e}")

    return None


# ---------------------------------------------------------------------------
# Combined scorer
# ---------------------------------------------------------------------------

def score_job(job) -> dict:
    """Score a job using local matching + optional AI. Returns scoring dict."""
    local_score = score_job_local(job)

    result = {
        "local_score": round(local_score, 3),
        "ai_score": None,
        "ai_reasons": [],
        "ai_missing_skills": [],
        "ai_recommendation": None,
        "final_score": round(local_score, 3),
    }

    # Use AI scoring for jobs that pass the minimum threshold
    if local_score >= SEARCH_PREFERENCES["min_experience_match"]:
        ai_result = score_job_ai(job)
        if ai_result:
            result["ai_score"] = ai_result.get("score")
            result["ai_reasons"] = ai_result.get("reasons", [])
            result["ai_missing_skills"] = ai_result.get("missing_skills", [])
            result["ai_recommendation"] = ai_result.get("recommendation")
            # Weighted average: 40% local + 60% AI
            if result["ai_score"] is not None:
                result["final_score"] = round(
                    0.4 * local_score + 0.6 * result["ai_score"], 3
                )

    return result


def rank_jobs(jobs: list, min_score: float | None = None) -> list[tuple]:
    """Score and rank all jobs. Returns list of (job, score_dict) sorted by score desc.

    If *min_score* is given, only jobs meeting that threshold are returned.
    Pass ``min_score=0`` (or omit) to return **all** jobs with their scores.
    """
    scored = []
    for job in jobs:
        score_data = score_job(job)
        if min_score and score_data["final_score"] < min_score:
            continue
        scored.append((job, score_data))

    scored.sort(key=lambda x: x[1]["final_score"], reverse=True)
    return scored
