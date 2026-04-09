"""Configuration and resume profile for the job application bot."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- API Keys (optional) ---
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
JSEARCH_API_KEY  = os.getenv("JSEARCH_API_KEY", "")
ADZUNA_APP_ID    = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY   = os.getenv("ADZUNA_APP_KEY", "")
SERPAPI_KEY      = os.getenv("SERPAPI_KEY", "")       # serpapi.com — Google Jobs aggregation
CAREERJET_AFFID  = os.getenv("CAREERJET_AFFID", "")   # careerjet.com — free affiliate API

# --- Database ---
MONGO_URI = os.getenv("MONGO_URI", "")

# SQLite fallback (only used if MONGO_URI is not set)
_default_db_dir = os.path.join(os.path.dirname(__file__), "data")
if os.environ.get("RENDER") or not os.access(os.path.dirname(__file__), os.W_OK):
    _default_db_dir = os.path.join("/tmp", "jobbot_data")  # nosec B108
os.makedirs(_default_db_dir, exist_ok=True)
DB_PATH = os.path.join(_default_db_dir, "jobs.db")

# --- Resume Profile ---
PROFILE = {
    "name": "Rajesh Singh Kadyan",
    "title": "Senior Backend Engineer · SDE-3",
    "email": "rajeshsinghkadyan@gmail.com",
    "phone": "+91 8168481271",
    "location": "Rohtak, India",
    "years_of_experience": 6.8,
    "open_to": "Global Remote Roles",
    "summary": (
        "Senior Backend Engineer with 6.8 years building high-throughput "
        "distributed systems at 10K+ RPS for global enterprise clients. "
        "Delivered measurable impact: 40% latency reduction, 30% DB performance gain, "
        "99.9% uptime, 1M+ concurrent users. Own end-to-end system design (HLD/LLD), "
        "drive architecture decisions, and lead cross-functional teams across 4 time zones."
    ),
    "skills": {
        "languages": ["Java", "Python", "JavaScript", "SQL", "C++"],
        "backend": ["Spring Boot", "Spring Security", "Spring Data JPA", "Hibernate", "FastAPI", "Kafka"],
        "frontend": ["React.js", "Next.js", "Tailwind CSS"],
        "databases": ["PostgreSQL", "Oracle SQL", "MySQL", "MongoDB", "Redis", "Elasticsearch"],
        "cloud_devops": ["AWS", "EC2", "Lambda", "S3", "RDS", "SQS", "ECS", "CloudWatch", "GCP", "Docker", "GitHub Actions", "CI/CD"],
        "architecture": ["Microservices", "REST APIs", "Event-Driven", "Distributed Systems", "HLD", "LLD", "DDD"],
        "testing": ["JUnit", "Mockito", "Selenium", "TDD"],
    },
    "experience": [
        {
            "title": "Senior Engineer – Applications & Platforms",
            "company": "Brillio Technologies",
            "period": "Jun 2023 – Present",
            "highlights": [
                "Owned end-to-end architecture of scalable REST APIs at 10K+ RPS, reducing latency by 40%",
                "Cloud-native microservices on AWS Lambda & GCP Cloud Run — 99.9% uptime",
                "Improved Oracle SQL & PostgreSQL performance by 30%",
                "Built React.js dashboards, automated CI/CD cutting releases by 50%",
                "Mentored 5+ engineers, standardized API practices across 3 teams",
            ],
        },
        {
            "title": "Full-Stack Engineer (Freelance – Remote)",
            "company": "US, UK, EU & Dubai Clients",
            "period": "Feb 2023 – Jun 2023",
            "highlights": [
                "Spring Boot APIs + React frontends + Python (FastAPI) automation for international clients",
                "Migrated 3 enterprise monoliths to microservices",
            ],
        },
        {
            "title": "Software Engineer",
            "company": "IVY Comptech",
            "period": "Jan 2022 – Feb 2023",
            "highlights": [
                "Kafka-based event-driven systems for 1M+ concurrent users",
                "Redis caching, circuit breakers reducing cascading failures by 60%",
                "JVM profiling, heap/thread dump analysis, GC tuning",
            ],
        },
        {
            "title": "Project Engineer",
            "company": "Wipro Technologies",
            "period": "Jul 2021 – Jan 2022",
            "highlights": ["Backend modules for BFSI clients with OWASP-compliant security"],
        },
        {
            "title": "Freelance Backend Developer",
            "company": "Startups & SMBs",
            "period": "Apr 2019 – Jun 2021",
            "highlights": [
                "10+ backend applications for startups across ERP, e-commerce, SaaS",
                "Led remote teams of 3–5 engineers",
            ],
        },
    ],
    "education": "B.Tech – Computer Science Engineering | Chandigarh University | CGPA: 7.4/10 | 2021",
    "certifications": ["IBM Cloud Application Developer Mastery Award"],
}

# --- Location Preferences ---
LOCATION_PREFERENCES = {
    "default_country": os.getenv("DEFAULT_COUNTRY", "India"),
    "job_types": ["remote", "remote_in_country"],  # remote = worldwide, remote_in_country = remote within user's country
    "allowed_locations": [],  # empty = all locations allowed; populate to restrict
}

# --- Search Preferences ---
SEARCH_PREFERENCES = {
    "target_roles": [
        "Senior Backend Engineer",
        "Senior Software Engineer",
        "Backend Developer",
        "Java Developer",
        "Spring Boot Developer",
        "Full Stack Engineer",
        "SDE-3",
        "Software Engineer III",
        "Platform Engineer",
        "Python Developer",
        "Senior Java Developer",
    ],
    "keywords": [
        "java", "spring boot", "python", "backend", "microservices",
        "distributed systems", "kafka", "aws", "react", "postgresql",
        "remote", "fastapi", "docker", "kubernetes",
    ],
    "exclude_keywords": [
        "intern", "internship", "junior", "entry level", "trainee",
        "unpaid", "volunteer",
    ],
    "job_type": "remote",
    "min_experience_match": 0.3,  # minimum 30% skill match to consider
}
