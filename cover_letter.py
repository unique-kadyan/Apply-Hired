"""Cover letter generator — compelling, achievement-driven letters that recruiters remember.

Philosophy:
- Every letter opens with a specific hook (metric or company-specific insight)
- Achievements are quantified — numbers beat adjectives every time
- Role-specific language extracted from the JD makes the letter feel tailored
- Two A/B tones: "formal" (polished) and "direct" (punchy, confident)
  Both are tracked so we can measure which gets more interview callbacks.
"""

import logging
import random
import re
from typing import Optional

from jinja2 import Template

from config import PROFILE as _GLOBAL_PROFILE

logger = logging.getLogger(__name__)


def _resolve_profile(profile_data: dict | None) -> dict:
    return profile_data if profile_data else _GLOBAL_PROFILE


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
        if re.search(rf"\b{re.escape(skill.lower())}\b", text) and skill not in matching:
            matching.append(skill)
    return matching[:6]


def _best_highlights(profile: dict, max_items: int = 4) -> list[str]:
    """Pull the most metric-rich highlights from experience entries."""
    all_highlights = []
    for exp in (profile.get("experience") or [])[:4]:
        if isinstance(exp, dict):
            for h in (exp.get("highlights") or []):
                all_highlights.append(h)
    # Prefer highlights with numbers (%, x, k, M) — they're more persuasive
    scored = sorted(all_highlights, key=lambda h: len(re.findall(r'\d+', h)), reverse=True)
    return scored[:max_items]


def _job_signals(job_description: str) -> dict:
    """Extract signals from JD to personalise the letter."""
    desc = job_description.lower()
    signals = {}
    if any(w in desc for w in ["10k", "million", "1m", "10m", "high-traffic", "scale", "throughput"]):
        signals["scale"] = True
    if any(w in desc for w in ["microservice", "distributed", "event-driven", "kafka"]):
        signals["distributed"] = True
    if any(w in desc for w in ["mentor", "lead", "principal", "staff", "architecture"]):
        signals["leadership"] = True
    if any(w in desc for w in ["cloud", "aws", "gcp", "azure", "kubernetes"]):
        signals["cloud"] = True
    if any(w in desc for w in ["startup", "fast-paced", "move fast", "iterate"]):
        signals["startup"] = True
    if any(w in desc for w in ["fintech", "finance", "banking", "payments"]):
        signals["fintech"] = True
    if any(w in desc for w in ["ai", "ml", "machine learning", "llm", "data"]):
        signals["ai_ml"] = True
    return signals


# ---------------------------------------------------------------------------
# Template: Formal (polished, authoritative)
# ---------------------------------------------------------------------------

_FORMAL_TEMPLATE = """\
Dear Hiring Team at {{ company }},

{% if top_metric %}{{ top_metric }} — that's the kind of impact I've built a career around delivering. {% endif %}\
As a {{ title }} with {{ years }} years of experience, I'm applying for the {{ job_title }} role at {{ company }} \
because {% if company_hook %}{{ company_hook }}{% else %}it sits squarely at the intersection of my expertise and ambition{% endif %}.

What I will bring to {{ company }}:

{% for point in key_points %}• {{ point }}
{% endfor %}
{% if matching_skills %}The role's requirements map directly to my hands-on expertise in {{ matching_skills | join(', ') }}.{% endif %}

I'd welcome the opportunity to discuss how I can drive measurable outcomes for {{ company }}. \
Available at {{ email }}{% if phone %} or {{ phone }}{% endif %}.

Sincerely,
{{ name }}
"""

# ---------------------------------------------------------------------------
# Template: Direct (confident, punchy — works well for startup/tech roles)
# ---------------------------------------------------------------------------

_DIRECT_TEMPLATE = """\
Hi {{ company }} Team,

I'm {{ name }}, a {{ title }} who has spent {{ years }} years shipping systems that scale{% if top_metric %} — most recently {{ top_metric }}{% endif %}.

Why I'm reaching out: {{ job_title }} at {{ company }} checks every box for what I want next. \
{% if company_hook %}{{ company_hook }}. {% endif %}\
{% if matching_skills %}You need {{ matching_skills[:3] | join(', ') }} — I've been doing that in production.{% endif %}

Here's what I've delivered that's directly relevant:

{% for point in key_points %}→ {{ point }}
{% endfor %}
I keep my applications short because I respect your time. If the above looks interesting, I'm ready for a call.

{{ name }} · {{ email }}{% if phone %} · {{ phone }}{% endif %}
"""


def _build_key_points(profile: dict, signals: dict, matching_skills: list[str]) -> list[str]:
    """Build 3-4 concrete, role-relevant bullet points."""
    highlights = _best_highlights(profile, max_items=6)
    points = []

    # Map signals to relevant highlights
    signal_keywords = {
        "scale":       ["rps", "latency", "throughput", "concurrent", "traffic", "uptime", "performance"],
        "distributed": ["kafka", "microservice", "event-driven", "distributed", "queue"],
        "leadership":  ["mentor", "lead", "architecture", "team", "design", "hld", "lld"],
        "cloud":       ["aws", "gcp", "docker", "kubernetes", "lambda", "cloud"],
        "fintech":     ["bfsi", "payment", "finance", "compliance", "security"],
    }

    used = set()
    for signal, keywords in signal_keywords.items():
        if signal in signals:
            for h in highlights:
                if any(kw in h.lower() for kw in keywords) and h not in used:
                    points.append(h)
                    used.add(h)
                    break
        if len(points) >= 3:
            break

    # Fill remaining slots with best remaining highlights
    for h in highlights:
        if h not in used and len(points) < 4:
            points.append(h)
            used.add(h)

    # If still short, add a skill-based point
    if len(points) < 2 and matching_skills:
        points.append(f"Production expertise in {', '.join(matching_skills[:3])}")

    return points[:4]


def _company_hook(job, signals: dict) -> str:
    """Generate a specific sentence about why this company/role is appealing."""
    hooks = []
    if signals.get("scale"):
        hooks.append(f"building high-scale systems is exactly the engineering challenge I thrive in")
    if signals.get("distributed"):
        hooks.append(f"the event-driven, distributed architecture aligns with systems I've built for production")
    if signals.get("leadership"):
        hooks.append(f"the opportunity to drive architecture decisions and mentor engineers is where I do my best work")
    if signals.get("startup"):
        hooks.append(f"the fast-paced, ownership-driven environment matches how I've worked best")
    if signals.get("fintech"):
        hooks.append(f"I have a proven track record in high-compliance, high-stakes financial systems")
    return hooks[0] if hooks else ""


def _top_metric(profile: dict) -> str:
    """Extract the single most impressive metric from the profile."""
    candidates = []
    for exp in (profile.get("experience") or [])[:3]:
        for h in (exp.get("highlights") or [])[:3]:
            nums = re.findall(r'\d+', h)
            if nums and max(int(n) for n in nums) >= 10:
                candidates.append((max(int(n) for n in nums), h))
    if not candidates:
        return ""
    _, best = sorted(candidates, reverse=True)[0]
    # Shorten to a punchy fragment
    best = best.strip().rstrip('.')
    return best[0].lower() + best[1:] if best else ""


def generate_cover_letter_template(job, profile_data: dict | None = None, tone: str = "formal") -> str:
    profile = _resolve_profile(profile_data)
    matching_skills = _find_matching_skills(job.description, job.tags, profile)
    signals = _job_signals(job.description)
    key_points = _build_key_points(profile, signals, matching_skills)
    hook = _company_hook(job, signals)
    metric = _top_metric(profile)

    tmpl_str = _DIRECT_TEMPLATE if tone == "direct" else _FORMAL_TEMPLATE
    template = Template(tmpl_str)
    return template.render(
        company=job.company,
        job_title=job.title,
        name=profile.get("name", ""),
        title=profile.get("title", "Software Engineer").split("·")[0].strip(),
        years=profile.get("years_of_experience", ""),
        email=profile.get("email", ""),
        phone=profile.get("phone", ""),
        matching_skills=matching_skills,
        key_points=key_points,
        company_hook=hook,
        top_metric=metric,
    )


# ---------------------------------------------------------------------------
# AI-powered cover letter — unique, achievement-driven, recruiter-optimised
# ---------------------------------------------------------------------------

def generate_cover_letter_ai(job, profile_data: dict | None = None) -> Optional[str]:
    from resume_parser import _build_ai_providers, _call_ai_text, _is_quota_error

    providers = _build_ai_providers()
    if not providers:
        return None

    profile = _resolve_profile(profile_data)
    tone = getattr(generate_cover_letter_ai, "_ab_tone", "formal")

    skills_text = ", ".join(_flatten_skills(profile)[:20]) or "software engineering"
    highlights = _best_highlights(profile, max_items=5)
    highlights_text = "\n".join(f"- {h}" for h in highlights) or "(not provided)"
    signals = _job_signals(job.description)
    matching = _find_matching_skills(job.description, job.tags, profile)

    experience_summary = ""
    for exp in (profile.get("experience") or [])[:3]:
        if isinstance(exp, dict):
            h = "; ".join((exp.get("highlights") or [])[:2])
            experience_summary += f"- {exp.get('title','')} @ {exp.get('company','')} ({exp.get('period','')}): {h}\n"

    tone_guide = {
        "formal": (
            "Tone: Formal and authoritative. Opening: 'Dear Hiring Team at [Company],'. "
            "Third person references allowed. No contractions. Structured paragraphs."
        ),
        "direct": (
            "Tone: Direct, confident, and punchy — think senior engineer writing to an equal, not a gatekeeper. "
            "Opening: 'Hi [Company] Team,' — short sentences, contractions are fine, zero filler words. "
            "Every sentence must earn its place."
        ),
    }.get(tone, "")

    jd_signals_text = ", ".join(k for k in signals.keys()) if signals else "general software engineering"

    prompt = f"""You are an expert cover letter writer for senior software engineers.
Write a cover letter that will make a recruiter STOP and schedule an interview.

RULES — strictly follow all:
1. {tone_guide}
2. Open with ONE punchy sentence that references a specific metric from the candidate's experience. NO "I am writing to express..."
3. Never use these phrases: "I am writing", "passion for", "team player", "hardworking", "quick learner", "results-driven", "I believe", "leverage", "synergy"
4. Include 3-4 achievement bullets with real numbers from the profile highlights
5. Reference at least 2 specific requirements from the job description
6. Total word count: 220-300 words. Shorter is better.
7. End with ONE clear call-to-action sentence + candidate name + email
8. Do NOT fabricate any metric, skill, or experience. Only use what's in the profile.
9. Output ONLY the cover letter text — no subject line, no "---", no commentary.

CANDIDATE:
Name: {profile.get('name', '')}
Current Title: {profile.get('title', '')}
Experience: {profile.get('years_of_experience', '')} years
Skills: {skills_text}
Summary: {profile.get('summary', '')}
Top Achievements:
{highlights_text}
Recent Experience:
{experience_summary or '(not provided)'}
Contact: {profile.get('email', '')} | {profile.get('phone', '')}

JOB:
Title: {job.title}
Company: {job.company}
Key Requirements (from JD): {jd_signals_text}
Matching Skills: {', '.join(matching) or 'see profile'}
JD Excerpt: {job.description[:900]}
"""

    for provider in providers:
        try:
            result = _call_ai_text(provider, prompt)
            if result and len(result) > 80:
                logger.info(f"Cover letter ({tone}) generated via {provider['name']}")
                return result.strip()
        except Exception as e:
            if _is_quota_error(e):
                continue
            logger.warning(f"Cover letter failed ({provider['name']}): {e}")
            continue
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_cover_letter(job, profile_data: dict | None = None) -> tuple[str, str]:
    """Generate a compelling cover letter (AI → template fallback).

    Returns (letter_text, tone). Tone is randomly assigned ("formal" | "direct")
    for A/B tracking — callers must persist it as cover_letter_tone on the job doc.
    """
    tone = random.choice(["formal", "direct"])
    generate_cover_letter_ai._ab_tone = tone

    ai_letter = generate_cover_letter_ai(job, profile_data)
    if ai_letter:
        return ai_letter, tone
    return generate_cover_letter_template(job, profile_data, tone=tone), tone


# ---------------------------------------------------------------------------
# Profile completeness check
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "name":                "Full name",
    "email":               "Email address",
    "phone":               "Phone number",
    "title":               "Job title / current role",
    "years_of_experience": "Years of experience",
    "summary":             "Professional summary",
}

OPTIONAL_FIELDS = {
    "linkedin": "LinkedIn URL",
    "github":   "GitHub username / URL",
    "location": "Location",
}


def check_profile_completeness(profile: dict) -> dict:
    """Returns {missing, warnings, is_complete}."""
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
