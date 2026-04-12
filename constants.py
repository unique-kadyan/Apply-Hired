"""Shared domain constants — single source of truth for the entire application.

Rules:
- All magic numbers, domain lists, and tunable thresholds live here.
- Backend imports directly.  Frontend consumes via /api/config (routes/config.py).
- Pure Python — no imports from application modules.
"""

import os

# ── Search & job-age ────────────────────────────────────────────────────────
JOB_MAX_AGE_DAYS: int = int(os.getenv("JOB_MAX_AGE_DAYS", 120))
MAX_SEARCH_QUERIES: int = int(os.getenv("MAX_SEARCH_QUERIES", 10))
MAX_SKILLS_FOR_QUERIES: int = int(os.getenv("MAX_SKILLS_FOR_QUERIES", 4))
DUPLICATE_DETECTION_DAYS: int = int(os.getenv("DUPLICATE_DETECTION_DAYS", 7))

# Minimum score (0–1) for a job to be surfaced to the user
MIN_JOB_MATCH_SCORE: float = float(os.getenv("MIN_JOB_MATCH_SCORE", 0.3))

# Blended scoring weights (local heuristics vs AI score)
LOCAL_SCORE_WEIGHT: float = float(os.getenv("LOCAL_SCORE_WEIGHT", 0.4))
AI_SCORE_WEIGHT: float = float(os.getenv("AI_SCORE_WEIGHT", 0.6))

# ── Seniority scoring adjustments ───────────────────────────────────────────
JUNIOR_ROLE_PENALTY: float = float(os.getenv("JUNIOR_ROLE_PENALTY", 0.3))
SENIOR_ROLE_BONUS: float = float(os.getenv("SENIOR_ROLE_BONUS", 0.1))
OVERQUALIFIED_PENALTY_PER_YEAR: float = float(os.getenv("OVERQUALIFIED_PENALTY_PER_YEAR", 0.1))
OVERQUALIFIED_PENALTY_CAP: float = float(os.getenv("OVERQUALIFIED_PENALTY_CAP", 0.35))

TITLE_EXACT_MATCH_BONUS: float = float(os.getenv("TITLE_EXACT_MATCH_BONUS", 0.2))
TITLE_KEYWORD_BONUS_PER_MATCH: float = float(os.getenv("TITLE_KEYWORD_BONUS_PER_MATCH", 0.05))
TITLE_KEYWORD_BONUS_CAP: float = float(os.getenv("TITLE_KEYWORD_BONUS_CAP", 0.15))

REMOTE_LOCATION_BONUS: float = float(os.getenv("REMOTE_LOCATION_BONUS", 0.05))
CITY_MATCH_BONUS: float = float(os.getenv("CITY_MATCH_BONUS", 0.10))

# ── Experience levels (shared by matcher + frontend) ────────────────────────
# Each entry: (min_years_inclusive, max_years_exclusive | None = no cap)
EXPERIENCE_LEVELS: dict[str, tuple[int, int | None]] = {
    "Junior":     (0,  2),
    "Mid-Level":  (2,  5),
    "Senior":     (5,  8),
    "Lead":       (7,  12),
    "Staff":      (10, 15),
    "Principal":  (12, None),
}

# Label shown to user alongside level name
EXPERIENCE_LEVEL_LABELS: dict[str, str] = {
    "Junior":     "0–2 yrs",
    "Mid-Level":  "2–5 yrs",
    "Senior":     "5–8 yrs",
    "Lead":       "7–12 yrs",
    "Staff":      "10–15 yrs",
    "Principal":  "12+ yrs",
}

# ── Role-title keyword hints (matcher heuristics) ───────────────────────────
ROLE_TITLE_KEYWORDS: frozenset[str] = frozenset({
    "senior", "backend", "engineer", "developer", "java", "python",
    "spring", "full stack", "sde", "platform",
})

# ── Language/skill conflict map (prevents Java → JavaScript mismatches) ──────
LANGUAGE_CONFLICTS: dict[str, list[str]] = {
    "java":    ["javascript", "javafx"],
    "c":       ["c++", "c#", "objective-c", "cobol", "clojure"],
    "go":      ["golang"],
    "r":       ["ruby", "rust", "rails"],
    "python":  [],
    "kotlin":  [],
    "swift":   [],
    "rust":    ["rustic"],
    "perl":    ["perlite"],
    "dart":    [],
    "scala":   [],
    "spring":  [],
}

# ── Resume scoring rubric (structured scorer + optimizer prompt) ─────────────
BULLETS_PER_ROLE_TARGET: int = int(os.getenv("BULLETS_PER_ROLE_TARGET", 5))
MAX_OPTIMIZATION_PASSES: int = int(os.getenv("MAX_OPTIMIZATION_PASSES", 5))
REFINABLE_SECTIONS: frozenset[str] = frozenset({"summary", "skills", "experience", "ats_keywords", "formatting"})

SUMMARY_MIN_SENTENCES_EXCELLENT: int = 4
SUMMARY_MIN_WORDS_EXCELLENT: int = 80
SUMMARY_MIN_METRICS_EXCELLENT: int = 3
SUMMARY_SCORE_EXCELLENT: int = 10

SUMMARY_MIN_SENTENCES_GOOD: int = 3
SUMMARY_MIN_WORDS_GOOD: int = 50
SUMMARY_MIN_METRICS_GOOD: int = 1
SUMMARY_SCORE_GOOD: int = 7

SUMMARY_SCORE_MIN: int = 4

SKILLS_COUNT_EXCELLENT: int = 20
SKILLS_SCORE_EXCELLENT: int = 15
SKILLS_COUNT_GOOD: int = 12
SKILLS_SCORE_GOOD: int = 10
SKILLS_SCORE_MIN: int = 6

EXP_BULLET_RATIO_EXCELLENT: float = 0.9
EXP_METRIC_RATIO_EXCELLENT: float = 0.8
EXP_SCORE_EXCELLENT: int = 25
EXP_BULLET_RATIO_GOOD: float = 0.7
EXP_METRIC_RATIO_GOOD: float = 0.5
EXP_SCORE_GOOD: int = 18
EXP_SCORE_MIN: int = 10

EDUCATION_SCORE_COMPLETE: int = 10
EDUCATION_SCORE_PARTIAL: int = 6
EDUCATION_SCORE_MINIMAL: int = 3

FORMAT_SCORE_COMPLETE: int = 15
FORMAT_SCORE_PARTIAL: int = 10
FORMAT_SCORE_MIN: int = 5

ATS_KW_COUNT_EXCELLENT: int = 20
ATS_KW_SCORE_EXCELLENT: int = 15
ATS_KW_COUNT_GOOD: int = 10
ATS_KW_SCORE_GOOD: int = 10
ATS_KW_SCORE_MIN: int = 5

CONTACT_INFO_SCORE_MAP: dict[int, int] = {4: 10, 3: 7, 2: 5, 1: 2, 0: 0}

# ── Schedule options (frontend auto-search intervals) ───────────────────────
SCHEDULE_INTERVAL_OPTIONS: list[int] = [
    int(h) for h in os.getenv("SCHEDULE_INTERVAL_OPTIONS", "6,12,24,48").split(",")
]
DEFAULT_SCHEDULE_INTERVAL_HOURS: int = int(os.getenv("DEFAULT_SCHEDULE_INTERVAL_HOURS", 24))

# ── Salary search UI defaults ────────────────────────────────────────────────
SALARY_MIN_USD: int = int(os.getenv("SALARY_MIN_USD", 0))
SALARY_MAX_USD: int = int(os.getenv("SALARY_MAX_USD", 300_000))
SALARY_STEP_USD: int = int(os.getenv("SALARY_STEP_USD", 10_000))
SALARY_LABEL_BREAKPOINTS: list[int] = [50_000, 100_000, 150_000, 200_000, 300_000]

# ── Country list (search & schedule UI) ─────────────────────────────────────
COUNTRY_OPTIONS: list[dict] = [
    {"value": "USA",       "label": "United States (USA)"},
    {"value": "UK",        "label": "United Kingdom (UK)"},
    {"value": "Canada",    "label": "Canada"},
    {"value": "Germany",   "label": "Germany"},
    {"value": "Netherlands", "label": "Netherlands"},
    {"value": "India",     "label": "India"},
    {"value": "Australia", "label": "Australia"},
    {"value": "Singapore", "label": "Singapore"},
    {"value": "UAE",       "label": "UAE / Dubai"},
    {"value": "France",    "label": "France"},
    {"value": "Spain",     "label": "Spain"},
    {"value": "Ireland",   "label": "Ireland"},
    {"value": "Sweden",    "label": "Sweden"},
    {"value": "Switzerland", "label": "Switzerland"},
    {"value": "Japan",     "label": "Japan"},
    {"value": "Brazil",    "label": "Brazil"},
    {"value": "Europe",    "label": "Europe (Any)"},
    {"value": "APAC",      "label": "Asia-Pacific (Any)"},
    {"value": "LATAM",     "label": "Latin America (Any)"},
]

# ── Action verbs for resume bullet scoring ───────────────────────────────────
ACTION_VERBS: frozenset[str] = frozenset({
    "led", "built", "designed", "developed", "architected", "reduced",
    "increased", "optimized", "delivered", "managed", "launched", "scaled",
    "improved", "automated", "migrated", "implemented", "created", "deployed",
    "mentored", "established", "streamlined", "accelerated", "engineered",
    "drove", "spearheaded", "transformed", "achieved", "boosted", "cut",
    "saved", "grew", "collaborated", "integrated", "refactored", "enhanced",
    "owned", "shipped", "authored", "consolidated", "introduced", "debugged",
    "rewrote", "revamped", "coordinated", "resolved",
})

# ── Stats / analytics UI ────────────────────────────────────────────────────
SCORE_DISTRIBUTION_BUCKETS: list[float] = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
TOP_COMPANIES_LIMIT: int = int(os.getenv("TOP_COMPANIES_LIMIT", 8))
DAILY_ACTIVITY_DAYS: int = int(os.getenv("DAILY_ACTIVITY_DAYS", 14))

# ── Search status poll interval (ms, used by frontend) ──────────────────────
SEARCH_POLL_INTERVAL_MS: int = int(os.getenv("SEARCH_POLL_INTERVAL_MS", 2000))
SCHEDULE_REFRESH_INTERVAL_MS: int = int(os.getenv("SCHEDULE_REFRESH_INTERVAL_MS", 60_000))
