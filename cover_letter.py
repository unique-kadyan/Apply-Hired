"""Cover letter generator — template-based + optional AI-powered, per-user profile."""

import logging
from typing import Optional

from jinja2 import Template

from config import PROFILE as _GLOBAL_PROFILE

logger = logging.getLogger(__name__)


def _resolve_profile(profile_data: dict | None) -> dict:
    """Return the given profile, falling back to the global config profile."""
    return profile_data if profile_data else _GLOBAL_PROFILE


# ---------------------------------------------------------------------------
# Template-based cover letter (no API key needed)
# ---------------------------------------------------------------------------

COVER_LETTER_TEMPLATE = """Dear Hiring Team at {{ company }},

I am writing to express my strong interest in the {{ job_title }} position at {{ company }}. As a {{ profile.title or 'Software Engineer' }} with {{ profile.years_of_experience or 3 }} years of experience, I am excited about the opportunity to contribute to your team.

{% if matching_skills %}My technical background aligns closely with your requirements. I bring hands-on expertise in {{ matching_skills | join(', ') }}.{% endif %}

{% if top_highlights %}Some highlights from my recent experience:
{% for highlight in top_highlights %}• {{ highlight }}
{% endfor %}{% endif %}
{% if job_specific_points %}What specifically excites me about this role:
{% for point in job_specific_points %}• {{ point }}
{% endfor %}{% endif %}
I am actively seeking {{ profile.open_to or 'remote' }} opportunities and would welcome the chance to discuss how my background can contribute to {{ company }}'s engineering goals.

Thank you for considering my application. I look forward to speaking with your team.

Best regards,
{{ profile.name }}
{{ profile.email }}{% if profile.phone %} | {{ profile.phone }}{% endif %}
"""


def _flatten_skills(profile: dict) -> list[str]:
    skills = profile.get("skills", {})
    if isinstance(skills, dict):
        return [s for group in skills.values() for s in group]
    if isinstance(skills, list):
        return skills
    return []


def _find_matching_skills(job_description: str, job_tags: list[str], profile: dict) -> list[str]:
    text = f"{job_description} {' '.join(job_tags)}".lower()
    matching = []
    for skill in _flatten_skills(profile):
        if skill.lower() in text and skill not in matching:
            matching.append(skill)
    return matching[:8]


def _extract_job_specific_points(job_description: str) -> list[str]:
    points = []
    desc = job_description.lower()
    if any(w in desc for w in ["scale", "high-traffic", "performance", "throughput"]):
        points.append("The focus on scalable, high-performance systems aligns with my experience")
    if any(w in desc for w in ["microservice", "distributed", "event-driven"]):
        points.append("The microservices/distributed architecture matches my production background")
    if any(w in desc for w in ["mentor", "lead", "team", "cross-functional"]):
        points.append("The leadership aspect resonates with my experience guiding engineering teams")
    if any(w in desc for w in ["cloud", "aws", "gcp", "kubernetes", "docker"]):
        points.append("The cloud-native requirements match my hands-on cloud experience")
    if any(w in desc for w in ["ci/cd", "devops", "pipeline", "automation"]):
        points.append("The DevOps culture aligns with my track record building CI/CD pipelines")
    return points[:3]


def generate_cover_letter_template(job, profile_data: dict | None = None) -> str:
    profile = _resolve_profile(profile_data)
    matching_skills = _find_matching_skills(job.description, job.tags, profile)
    if not matching_skills:
        matching_skills = _flatten_skills(profile)[:5]

    # Pull highlights from experience array (if any)
    top_highlights = []
    for exp in (profile.get("experience") or [])[:3]:
        if isinstance(exp, dict) and exp.get("highlights"):
            top_highlights.append(exp["highlights"][0])

    job_specific_points = _extract_job_specific_points(job.description)

    template = Template(COVER_LETTER_TEMPLATE)
    return template.render(
        company=job.company,
        job_title=job.title,
        profile=profile,
        matching_skills=matching_skills,
        top_highlights=top_highlights[:3],
        job_specific_points=job_specific_points,
    )


# ---------------------------------------------------------------------------
# AI-powered cover letter (free provider chain)
# ---------------------------------------------------------------------------

def generate_cover_letter_ai(job, profile_data: dict | None = None) -> Optional[str]:
    from resume_parser import _build_ai_providers, _call_ai_text, _is_quota_error

    providers = _build_ai_providers()
    if not providers:
        return None

    profile = _resolve_profile(profile_data)
    skills_text = ", ".join(_flatten_skills(profile)[:20]) or "various software engineering skills"

    experience_text = ""
    for exp in (profile.get("experience") or [])[:3]:
        if isinstance(exp, dict):
            highlights = "; ".join((exp.get("highlights") or [])[:2])
            experience_text += f"- {exp.get('title', '')} at {exp.get('company', '')} ({exp.get('period', '')}): {highlights}\n"

    prompt = f"""Write a professional, concise cover letter (250-350 words) for this job application.

CANDIDATE PROFILE:
- Name: {profile.get('name', '')}
- Title: {profile.get('title', '')}
- Years of Experience: {profile.get('years_of_experience', '')}
- Key Skills: {skills_text}
- Summary: {profile.get('summary', '')}
- Recent Experience:
{experience_text or '(not provided)'}
- Email: {profile.get('email', '')}

JOB DETAILS:
- Title: {job.title}
- Company: {job.company}
- Description: {job.description[:1200]}

INSTRUCTIONS:
1. Address "Dear Hiring Team at {job.company}"
2. Highlight 3-4 specific skills/experiences that match the job
3. Include quantifiable achievements from the profile where possible
4. Show enthusiasm for the specific company/role
5. Keep it professional but personable
6. End with the candidate's name and email
7. Do NOT fabricate skills or experience not in the profile
8. Output only the cover letter text, no extra commentary
"""

    for provider in providers:
        try:
            result = _call_ai_text(provider, prompt)
            if result and len(result) > 50:
                logger.info(f"Cover letter generated with {provider['name']}")
                return result
        except Exception as e:
            if _is_quota_error(e):
                continue
            logger.warning(f"Cover letter failed ({provider['name']}): {e}")
            continue
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_cover_letter(job, profile_data: dict | None = None) -> str:
    """Generate the best cover letter available (AI → template fallback)."""
    ai_letter = generate_cover_letter_ai(job, profile_data)
    if ai_letter:
        return ai_letter
    return generate_cover_letter_template(job, profile_data)


# ---------------------------------------------------------------------------
# Profile completeness check
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "name":               "Full name",
    "email":              "Email address",
    "phone":              "Phone number",
    "title":              "Job title / current role",
    "years_of_experience": "Years of experience",
    "summary":            "Professional summary",
}

OPTIONAL_FIELDS = {
    "linkedin":  "LinkedIn URL",
    "github":    "GitHub username / URL",
    "location":  "Location",
}


def check_profile_completeness(profile: dict) -> dict:
    """
    Returns dict with:
      missing: [{field, label, type}]   — required fields that are empty
      warnings: [{field, label}]        — optional fields that are empty
      is_complete: bool
    """
    missing = []
    warnings = []

    for field, label in REQUIRED_FIELDS.items():
        val = profile.get(field)
        empty = (
            not val
            or (isinstance(val, str) and not val.strip())
            or (isinstance(val, (int, float)) and val == 0)
        )
        if empty:
            field_type = "number" if field == "years_of_experience" else "text"
            missing.append({"field": field, "label": label, "type": field_type})

    # Check skills
    skills = profile.get("skills", {})
    has_skills = (
        (isinstance(skills, dict) and any(skills.values()))
        or (isinstance(skills, list) and len(skills) > 0)
    )
    if not has_skills:
        missing.append({"field": "skills_text", "label": "Key skills (comma-separated)", "type": "text"})

    for field, label in OPTIONAL_FIELDS.items():
        val = profile.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            warnings.append({"field": field, "label": label})

    return {
        "missing": missing,
        "warnings": warnings,
        "is_complete": len(missing) == 0,
    }
