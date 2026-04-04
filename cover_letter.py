"""Cover letter generator — template-based + optional AI-powered."""

import logging
from typing import Optional

from jinja2 import Template

from config import PROFILE, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template-based cover letter (no API key needed)
# ---------------------------------------------------------------------------

COVER_LETTER_TEMPLATE = """Dear Hiring Team at {{ company }},

I am writing to express my strong interest in the {{ job_title }} position at {{ company }}. As a {{ profile.title }} with {{ profile.years_of_experience }} years of experience building high-throughput distributed systems serving 10K+ RPS for global enterprise clients, I am excited about the opportunity to bring my expertise to your team.

My technical background aligns closely with your requirements. I bring deep, production-tested expertise in {{ matching_skills | join(', ') }}, backed by measurable results:

{% for highlight in top_highlights %}• {{ highlight }}
{% endfor %}
At {{ profile.experience[0].company }}, I currently own end-to-end architecture decisions for cloud-native microservices, driving 99.9% uptime and mentoring engineering teams across multiple time zones — experience that translates directly to delivering impact in a remote-first environment.

{% if job_specific_points %}What specifically excites me about this role:
{% for point in job_specific_points %}• {{ point }}
{% endfor %}{% endif %}
I am actively seeking global remote opportunities and would welcome the chance to discuss how my track record of {{ primary_skills }} expertise and system-level thinking can contribute to {{ company }}'s engineering goals.

Thank you for considering my application. I look forward to the conversation.

Best regards,
{{ profile.name }}
{{ profile.email }} | {{ profile.phone }}
"""


def _find_matching_skills(job_description: str, job_tags: list[str]) -> list[str]:
    """Find profile skills that match the job."""
    text = f"{job_description} {' '.join(job_tags)}".lower()
    matching = []
    for group_name, skills in PROFILE["skills"].items():
        for skill in skills:
            if skill.lower() in text and skill not in matching:
                matching.append(skill)
    return matching[:8]  # top 8


def _extract_job_specific_points(job_description: str) -> list[str]:
    """Extract key requirements from JD to personalize the letter."""
    points = []
    desc_lower = job_description.lower()

    if any(w in desc_lower for w in ["scale", "high-traffic", "performance", "throughput"]):
        points.append("The focus on scalable, high-performance systems matches my experience optimizing APIs to handle 10K+ RPS with 40% latency reduction")
    if any(w in desc_lower for w in ["microservice", "distributed", "event-driven"]):
        points.append("The microservices/distributed architecture aligns with my work building event-driven systems for 1M+ concurrent users")
    if any(w in desc_lower for w in ["mentor", "lead", "team", "cross-functional"]):
        points.append("The leadership aspect resonates with my experience mentoring 5+ engineers and driving standards across cross-functional teams")
    if any(w in desc_lower for w in ["cloud", "aws", "gcp", "kubernetes", "docker"]):
        points.append("The cloud-native requirements match my hands-on AWS/GCP experience with Lambda, ECS, and containerized deployments")
    if any(w in desc_lower for w in ["ci/cd", "devops", "pipeline", "automation"]):
        points.append("The DevOps culture aligns with my track record of building CI/CD pipelines adopted across 3 global teams")

    return points[:3]


def generate_cover_letter_template(job) -> str:
    """Generate a cover letter using the Jinja2 template."""
    matching_skills = _find_matching_skills(job.description, job.tags)
    if not matching_skills:
        matching_skills = ["Java", "Spring Boot", "Python", "AWS", "Microservices"]

    top_highlights = []
    for exp in PROFILE["experience"][:3]:
        if exp["highlights"]:
            top_highlights.append(exp["highlights"][0])

    primary_skills = ", ".join(matching_skills[:4])
    job_specific_points = _extract_job_specific_points(job.description)

    template = Template(COVER_LETTER_TEMPLATE)
    return template.render(
        company=job.company,
        job_title=job.title,
        profile=PROFILE,
        matching_skills=matching_skills,
        top_highlights=top_highlights[:3],
        primary_skills=primary_skills,
        job_specific_points=job_specific_points,
    )


# ---------------------------------------------------------------------------
# AI-powered cover letter (requires OpenAI API key)
# ---------------------------------------------------------------------------

def generate_cover_letter_ai(job) -> Optional[str]:
    """Generate a tailored cover letter using OpenAI GPT."""
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — skipping AI cover letter")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    skills_text = ", ".join(
        skill for group in PROFILE["skills"].values() for skill in group
    )

    experience_text = "\n".join(
        f"- {exp['title']} at {exp['company']} ({exp['period']}): {'; '.join(exp['highlights'][:2])}"
        for exp in PROFILE["experience"][:3]
    )

    prompt = f"""Write a professional, concise cover letter (250-350 words) for this job application.

CANDIDATE PROFILE:
- Name: {PROFILE['name']}
- Title: {PROFILE['title']}
- Experience: {PROFILE['years_of_experience']} years
- Key Skills: {skills_text}
- Summary: {PROFILE['summary']}
- Recent Experience:
{experience_text}
- Email: {PROFILE['email']}

JOB DETAILS:
- Title: {job.title}
- Company: {job.company}
- Description: {job.description[:2000]}

INSTRUCTIONS:
1. Address "Dear Hiring Team at {job.company}"
2. Highlight 3-4 specific skills/experiences that match the job
3. Include quantifiable achievements from the profile
4. Show enthusiasm for the specific company/role
5. Keep it professional but personable
6. End with contact details
7. Do NOT fabricate any skills or experience not in the profile
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"AI cover letter generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_cover_letter(job) -> str:
    """Generate the best cover letter available (AI if possible, else template)."""
    ai_letter = generate_cover_letter_ai(job)
    if ai_letter:
        return ai_letter
    return generate_cover_letter_template(job)
