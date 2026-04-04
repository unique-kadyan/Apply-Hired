"""Resume parser — extracts profile data from PDF/DOCX/TXT files."""

import re
import json
import logging
from pathlib import Path
from typing import Optional

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)


def extract_text_from_pdf(filepath: str) -> str:
    """Extract text from a PDF file."""
    from PyPDF2 import PdfReader
    reader = PdfReader(filepath)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_text_from_docx(filepath: str) -> str:
    """Extract text from a DOCX file."""
    from docx import Document
    doc = Document(filepath)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_txt(filepath: str) -> str:
    """Extract text from a TXT file."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text(filepath: str) -> str:
    """Extract text from any supported file format."""
    ext = Path(filepath).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    elif ext == ".txt":
        return extract_text_from_txt(filepath)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


# ---------------------------------------------------------------------------
# AI-powered parsing (with OpenAI API key)
# ---------------------------------------------------------------------------

def parse_resume_ai(text: str) -> Optional[dict]:
    """Use OpenAI GPT to parse resume text into structured profile data."""
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"""Parse this resume text and return a JSON object with exactly this structure.
Extract all real data from the resume. Do not fabricate anything.

Return ONLY valid JSON, no other text:

{{
    "name": "Full Name",
    "title": "Current Title / Role",
    "email": "email@example.com",
    "phone": "phone number",
    "location": "City, Country",
    "years_of_experience": 0.0,
    "open_to": "type of roles (e.g. Remote, Onsite, Hybrid)",
    "summary": "Professional summary in 2-3 sentences",
    "skills": {{
        "languages": ["list of programming languages"],
        "backend": ["backend frameworks/tools"],
        "frontend": ["frontend frameworks/tools"],
        "databases": ["databases"],
        "cloud_devops": ["cloud and devops tools"],
        "architecture": ["architecture patterns/practices"],
        "testing": ["testing tools/practices"]
    }},
    "experience": [
        {{
            "title": "Job Title",
            "company": "Company Name",
            "period": "Start – End",
            "highlights": ["achievement 1", "achievement 2"]
        }}
    ],
    "education": "degree and university info",
    "certifications": ["cert1", "cert2"]
}}

RESUME TEXT:
{text[:5000]}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        result_text = response.choices[0].message.content
        json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logger.error(f"AI resume parsing failed: {e}")

    return None


# ---------------------------------------------------------------------------
# Regex-based parsing (no API key needed)
# ---------------------------------------------------------------------------

# Common skill keywords to look for
SKILL_PATTERNS = {
    "languages": [
        "Java", "Python", "JavaScript", "TypeScript", "C\\+\\+", "C#", "Go",
        "Golang", "Rust", "Ruby", "PHP", "Kotlin", "Swift", "Scala", "SQL",
        "R", "Perl", "Dart", "Lua", "Shell", "Bash",
    ],
    "backend": [
        "Spring Boot", "Spring Security", "Spring Data", "Spring Cloud",
        "Hibernate", "FastAPI", "Django", "Flask", "Express\\.js", "NestJS",
        "Node\\.js", "Kafka", "RabbitMQ", "gRPC", "GraphQL", "REST API",
        "ASP\\.NET", "Ruby on Rails", "Laravel", "Gin", "Fiber",
    ],
    "frontend": [
        "React", "React\\.js", "Next\\.js", "Vue\\.js", "Angular",
        "Svelte", "Tailwind", "Bootstrap", "HTML5?", "CSS3?",
        "jQuery", "Redux", "Webpack", "Vite",
    ],
    "databases": [
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Oracle",
        "SQLite", "DynamoDB", "Cassandra", "Elasticsearch",
        "Firebase", "CouchDB", "MariaDB", "SQL Server", "Neo4j",
    ],
    "cloud_devops": [
        "AWS", "GCP", "Azure", "Docker", "Kubernetes", "K8s",
        "Terraform", "Ansible", "Jenkins", "GitHub Actions", "GitLab CI",
        "CI/CD", "CloudWatch", "EC2", "Lambda", "S3", "RDS", "SQS",
        "ECS", "EKS", "Fargate", "Heroku", "Vercel", "Netlify",
    ],
    "architecture": [
        "Microservices", "REST APIs?", "Event[- ]Driven", "Distributed Systems?",
        "HLD", "LLD", "DDD", "Domain[- ]Driven", "CQRS", "Serverless",
        "SOA", "Monolith", "API Gateway",
    ],
    "testing": [
        "JUnit", "Mockito", "Selenium", "Cypress", "Jest", "Mocha",
        "PyTest", "TDD", "BDD", "Integration Testing", "Unit Testing",
        "Performance Testing", "Load Testing",
    ],
}


def _extract_email(text: str) -> str:
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group() if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"[\+]?[\d\s\-\(\)]{10,15}", text)
    return match.group().strip() if match else ""


def _extract_name(text: str) -> str:
    """Attempt to extract name from first few lines."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        # Name is typically the first non-empty line, all caps or title case
        clean = re.sub(r"[^a-zA-Z\s]", "", line).strip()
        words = clean.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return clean
    return lines[0] if lines else ""


def _extract_skills(text: str) -> dict[str, list[str]]:
    """Extract skills by matching known patterns."""
    found = {}
    for group, patterns in SKILL_PATTERNS.items():
        matches = []
        for pattern in patterns:
            if re.search(rf"\b{pattern}\b", text, re.IGNORECASE):
                # Use the clean version of the pattern
                clean = pattern.replace("\\.", ".").replace("\\+", "+").replace("?", "").replace("s?", "s")
                if clean not in matches:
                    matches.append(clean)
        found[group] = matches
    return found


def _extract_experience_years(text: str) -> float:
    """Estimate years of experience from text."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?years?\s*(?:of\s*)?(?:experience)?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))

    # Try to calculate from date ranges
    year_pattern = re.findall(r"(20\d{2})\s*[–\-]\s*(20\d{2}|Present)", text, re.IGNORECASE)
    if year_pattern:
        import datetime
        total_years = 0
        current_year = datetime.datetime.now().year
        for start, end in year_pattern:
            end_year = current_year if end.lower() == "present" else int(end)
            total_years += end_year - int(start)
        return round(total_years, 1)

    return 0.0


def _extract_summary(text: str) -> str:
    """Extract summary/objective section."""
    patterns = [
        r"(?:SUMMARY|OBJECTIVE|ABOUT|PROFILE)\s*[:\n]\s*(.+?)(?:\n\n|\n[A-Z]{2,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            summary = match.group(1).strip()
            return re.sub(r"\s+", " ", summary)[:500]
    return ""


def _extract_experience(text: str) -> list[dict]:
    """Extract work experience entries."""
    entries = []
    # Look for patterns like "Title | Company" or "Title at Company" followed by dates
    exp_pattern = re.findall(
        r"(.+?)\s*[|–\-@at]+\s*(.+?)\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*[–\-]\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}))",
        text,
        re.IGNORECASE,
    )

    for title, company, period in exp_pattern[:6]:
        title = title.strip().split("\n")[-1].strip()
        company = company.strip().split("\n")[0].strip()
        entries.append({
            "title": title[:100],
            "company": company[:100],
            "period": period.strip(),
            "highlights": [],
        })

    # Extract bullet points near each entry
    bullets = re.findall(r"[•\-\*]\s*(.+?)(?:\n|$)", text)
    if entries and bullets:
        per_entry = max(1, len(bullets) // max(len(entries), 1))
        for i, entry in enumerate(entries):
            start = i * per_entry
            entry["highlights"] = [b.strip()[:200] for b in bullets[start:start + per_entry]][:4]

    return entries


def _extract_education(text: str) -> str:
    """Extract education section."""
    match = re.search(
        r"(?:EDUCATION|ACADEMIC|QUALIFICATION)\s*[:\n]\s*(.+?)(?:\n\n|\n[A-Z]{2,}|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if match:
        return re.sub(r"\s+", " ", match.group(1).strip())[:300]
    return ""


def _extract_certifications(text: str) -> list[str]:
    """Extract certifications."""
    match = re.search(
        r"(?:CERTIFICATION|CERTIFICATE|LICENSES?)\s*[:\n]\s*(.+?)(?:\n\n|\n[A-Z]{2,}|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if match:
        certs = re.findall(r"[•\-\*]\s*(.+?)(?:\n|$)", match.group(1))
        if certs:
            return [c.strip()[:200] for c in certs][:5]
        return [match.group(1).strip()[:200]]
    return []


def parse_resume_local(text: str) -> dict:
    """Parse resume using regex patterns (no API key needed)."""
    return {
        "name": _extract_name(text),
        "title": "",
        "email": _extract_email(text),
        "phone": _extract_phone(text),
        "location": "",
        "years_of_experience": _extract_experience_years(text),
        "open_to": "Remote",
        "summary": _extract_summary(text),
        "skills": _extract_skills(text),
        "experience": _extract_experience(text),
        "education": _extract_education(text),
        "certifications": _extract_certifications(text),
    }


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_resume(filepath: str) -> dict:
    """Parse a resume file and return structured profile data.
    Uses AI if available, falls back to regex parsing."""
    text = extract_text(filepath)

    if not text.strip():
        raise ValueError("Could not extract text from the resume file.")

    # Try AI parsing first
    ai_result = parse_resume_ai(text)
    if ai_result:
        logger.info("Resume parsed with AI")
        return ai_result

    # Fall back to local regex parsing
    logger.info("Resume parsed with regex (no API key)")
    return parse_resume_local(text)
