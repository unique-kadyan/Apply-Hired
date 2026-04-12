"""Payment routes — Razorpay order creation, verification, and resume optimization."""

import logging
import os
import random
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from constants import (
    ACTION_VERBS,
    ATS_KW_COUNT_EXCELLENT,
    ATS_KW_COUNT_GOOD,
    ATS_KW_SCORE_EXCELLENT,
    ATS_KW_SCORE_GOOD,
    ATS_KW_SCORE_MIN,
    BULLETS_PER_ROLE_TARGET,
    EDUCATION_SCORE_COMPLETE,
    EDUCATION_SCORE_MINIMAL,
    EDUCATION_SCORE_PARTIAL,
    EXP_BULLET_RATIO_EXCELLENT,
    EXP_BULLET_RATIO_GOOD,
    EXP_METRIC_RATIO_EXCELLENT,
    EXP_METRIC_RATIO_GOOD,
    EXP_SCORE_EXCELLENT,
    EXP_SCORE_GOOD,
    EXP_SCORE_MIN,
    FORMAT_SCORE_COMPLETE,
    FORMAT_SCORE_MIN,
    FORMAT_SCORE_PARTIAL,
    MAX_OPTIMIZATION_PASSES,
    REFINABLE_SECTIONS,
    SKILLS_COUNT_EXCELLENT,
    SKILLS_COUNT_GOOD,
    SKILLS_SCORE_EXCELLENT,
    SKILLS_SCORE_GOOD,
    SKILLS_SCORE_MIN,
    SUMMARY_MIN_METRICS_EXCELLENT,
    SUMMARY_MIN_METRICS_GOOD,
    SUMMARY_MIN_SENTENCES_EXCELLENT,
    SUMMARY_MIN_SENTENCES_GOOD,
    SUMMARY_MIN_WORDS_EXCELLENT,
    SUMMARY_MIN_WORDS_GOOD,
    SUMMARY_SCORE_EXCELLENT,
    SUMMARY_SCORE_GOOD,
    SUMMARY_SCORE_MIN,
)
from middleware import get_user_profile, is_admin, login_required
from services.currency import LOCATION_CURRENCY
from services.payment_service import (
    _key_id,
    create_order,
    is_configured,
    verify_payment,
)
from tracker import _get_db, update_user_profile

logger = logging.getLogger(__name__)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/payment")

_BASE_PRICE = int(os.environ.get("RESUME_PRICE_INR", 50))
_INTL_MARKUP = float(os.environ.get("INTL_MARKUP_PERCENT", 30)) / 100 + 1
_BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "INR")

_SYMBOLS = {
    "INR": "\u20b9",
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "AED": "AED ",
    "SGD": "S$",
    "AUD": "A$",
    "CAD": "C$",
    "JPY": "\u00a5",
}

_rate_cache = {"rates": {}, "fetched_at": 0}


def _fetch_exchange_rates() -> dict:
    import time

    now = time.time()
    if _rate_cache["rates"] and now - _rate_cache["fetched_at"] < 3600:
        return _rate_cache["rates"]
    try:
        import requests as req

        resp = req.get(
            f"https://api.exchangerate-api.com/v4/latest/{_BASE_CURRENCY}", timeout=5
        )
        _rate_cache["rates"] = resp.json().get("rates", {})
        _rate_cache["fetched_at"] = now
        return _rate_cache["rates"]
    except Exception:
        return _rate_cache.get("rates", {})


def _get_user_currency(profile: dict) -> str:
    location = (profile.get("location") or "").lower()
    # Allow env-var override: "india:INR,usa:USD" — falls back to shared LOCATION_CURRENCY map
    custom_map = os.environ.get("COUNTRY_CURRENCY_MAP", "")
    mapping: dict[str, str] = {}
    if custom_map:
        for pair in custom_map.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                mapping[parts[0].strip().lower()] = parts[1].strip().upper()
    if not mapping:
        mapping = LOCATION_CURRENCY
    for keyword, currency in mapping.items():
        if keyword in location:
            return currency
    return _BASE_CURRENCY


def _calculate_price(currency: str) -> dict:
    symbol = _SYMBOLS.get(currency, currency + " ")
    if currency == _BASE_CURRENCY:
        return {
            "currency": currency,
            "symbol": symbol,
            "display_amount": f"{symbol}{_BASE_PRICE}",
            "razorpay_amount": _BASE_PRICE * 100,
        }
    rates = _fetch_exchange_rates()
    rate = rates.get(currency, 0)
    if rate > 0:
        converted = _BASE_PRICE * rate * _INTL_MARKUP
        converted = round(converted) if converted >= 1 else round(converted, 2)
    else:
        converted = round(_BASE_PRICE * _INTL_MARKUP)
        currency = _BASE_CURRENCY
        symbol = _SYMBOLS.get(_BASE_CURRENCY, "")
    return {
        "currency": currency,
        "symbol": symbol,
        "display_amount": f"{symbol}{converted}",
        "razorpay_amount": (
            round(_BASE_PRICE * _INTL_MARKUP * 100)
            if currency != _BASE_CURRENCY
            else _BASE_PRICE * 100
        ),
    }


@payment_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    profile = get_user_profile(request.user)
    currency = _get_user_currency(profile)
    price = _calculate_price(currency)
    return jsonify(
        {
            "key_id": _key_id(),
            "amount": price["razorpay_amount"],
            "currency": "INR",
            "user_currency": currency,
            "display_amount": price["display_amount"],
            "configured": is_configured(),
        }
    )


@payment_bp.route("/create-order", methods=["POST"])
@login_required
def create_payment_order():
    if not is_configured():
        return jsonify({"error": "Payment gateway not configured"}), 500
    try:
        profile = get_user_profile(request.user)
        currency = _get_user_currency(profile)
        price = _calculate_price(currency)

        order = create_order(
            amount_paise=price["razorpay_amount"],
            receipt=f"r_{str(request.user['id'])[-8:]}_{int(datetime.now().timestamp())}",
        )
        db = _get_db()
        db.payments.insert_one(
            {
                "user_id": str(request.user["id"]),
                "order_id": order["id"],
                "amount": price["razorpay_amount"],
                "display_amount": price["display_amount"],
                "status": "created",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return jsonify(
            {
                "order_id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
                "key_id": _key_id(),
            }
        )
    except Exception as e:
        logger.error(f"Order creation failed: {e}")
        return jsonify({"error": "Failed to create payment order"}), 500


@payment_bp.route("/verify", methods=["POST"])
@login_required
def verify_payment_route():
    data = request.get_json() or {}
    order_id = data.get("order_id", "")
    payment_id = data.get("payment_id", "")
    signature = data.get("signature", "")

    if not order_id or not payment_id or not signature:
        return jsonify({"error": "Missing payment details"}), 400

    if not verify_payment(order_id, payment_id, signature):
        return jsonify({"error": "Payment verification failed"}), 400

    db = _get_db()
    db.payments.update_one(
        {"order_id": order_id, "user_id": str(request.user["id"])},
        {
            "$set": {
                "payment_id": payment_id,
                "signature": signature,
                "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return jsonify({"message": "Payment verified", "paid": True})


@payment_bp.route("/has-paid", methods=["GET"])
@login_required
def has_paid():
    if is_admin(request.user):
        return jsonify({"paid": True, "admin": True})
    db = _get_db()
    paid = db.payments.find_one(
        {
            "user_id": str(request.user["id"]),
            "status": "paid",
        }
    )
    return jsonify({"paid": bool(paid)})


def _str(val) -> str:
    """Coerce a value that should be a plain string to str.
    AI occasionally returns skill/keyword/highlight entries as dicts."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("name") or val.get("text") or val.get("value") or str(val)
    return str(val)


def _sanitize_optimized(data: dict) -> dict:
    """Guarantee that all leaf values the frontend renders as text are plain strings.
    Guards against AI hallucinating objects where strings are expected."""
    if not isinstance(data, dict):
        return data

    # summary
    if "summary" in data:
        data["summary"] = _str(data["summary"])

    # skills: each category must be a list of strings
    skills = data.get("skills") or {}
    if isinstance(skills, dict):
        for cat, vals in skills.items():
            if isinstance(vals, list):
                skills[cat] = [_str(v) for v in vals]
    data["skills"] = skills

    # experience: highlights and technologies must be lists of strings
    experience = data.get("experience") or []
    for exp in experience:
        if not isinstance(exp, dict):
            continue
        for field in ("title", "company", "period"):
            exp[field] = _str(exp.get(field, ""))
        exp["highlights"] = [_str(h) for h in (exp.get("highlights") or [])]
        exp["technologies"] = [_str(t) for t in (exp.get("technologies") or [])]
    data["experience"] = experience

    # flat string-list fields
    for field in ("ats_keywords", "optimization_notes", "certifications"):
        lst = data.get(field) or []
        if isinstance(lst, list):
            data[field] = [_str(v) for v in lst]

    return data


def _build_resume_text(profile: dict, optimized: dict) -> str:
    """Reconstruct ATS-friendly plain-text resume from profile + optimized JSON.
    Mirrors the structure and signals the AI scorer expects from a well-formatted resume.
    """
    lines = []
    if profile.get("name"):
        lines.append(profile["name"])
    if profile.get("title"):
        lines.append(profile["title"])

    contact = [
        x
        for x in [profile.get("email"), profile.get("phone"), profile.get("location")]
        if x
    ]
    if contact:
        lines.append(" | ".join(contact))

    linkedin = profile.get("linkedin") or profile.get("linkedin_url") or ""
    github = (
        profile.get("github_username")
        or profile.get("github")
        or profile.get("github_url")
        or ""
    )
    social_parts = []
    if linkedin:
        social_parts.append(f"LinkedIn: {linkedin}")
    if github:
        social_parts.append(f"GitHub: {github}")
    if social_parts:
        lines.append(" | ".join(social_parts))
    lines.append("")

    summary = optimized.get("summary", "")
    if summary:
        lines += ["SUMMARY", summary, ""]

    skills = optimized.get("skills", {})
    all_skill_names = [s for group in skills.values() for s in group if s]
    if all_skill_names:
        lines.append("SKILLS")
        for cat, vals in skills.items():
            if vals:
                lines.append(f"{cat.replace('_', ' ').title()}: {', '.join(vals)}")
        lines.append("")

    experience = optimized.get("experience", [])
    if experience:
        lines.append("EXPERIENCE")
        for exp in experience:
            title = exp.get("title", "")
            company = exp.get("company", "")
            period = exp.get("period", "")
            lines.append(f"{title} | {company} | {period}")
            for h in exp.get("highlights", []):
                lines.append(f"\u2022 {h}")
            lines.append("")

    education = profile.get("education", "")
    if education:
        lines += ["EDUCATION", education, ""]

    # Prefer certifications from optimized JSON (richer), fall back to profile
    certs = optimized.get("certifications") or profile.get("certifications", [])
    if certs:
        lines.append("CERTIFICATIONS")
        for c in certs:
            lines.append(f"\u2022 {c}")
        lines.append("")

    # ATS keywords section signals keyword density to the scorer
    ats_keywords = optimized.get("ats_keywords", [])
    if ats_keywords:
        lines += ["KEY COMPETENCIES", ", ".join(ats_keywords), ""]

    return "\n".join(lines)


_ACTION_VERBS = ACTION_VERBS  # imported from constants

_METRIC_RE = __import__("re").compile(
    r"\d+(?:\.\d+)?\s*(?:%|\+|[xX]|[KMB]|ms|RPS|TPS|GB|TB|MB|"
    r"users?|requests?|concurrent|parallel|engineers?|members?|teams?|"
    r"services?|nodes?|clusters?|pipelines?|endpoints?|modules?|"
    r"dashboards?|components?|repos?|hrs?\b|days?\b|months?\b|years?\b|"
    r"seconds?|minutes?|hours?|times?|fold|percent)"
    r"|\$\s*\d+(?:\.\d+)?"
    r"|\d+(?:\.\d+)?\s*[xX]\s"
    r"|(?:99|9\d)\.\d+\s*%"
)

_DEGREE_RE = __import__("re").compile(
    r"\b(bachelor|master|b\.?tech|b\.?e\.?|m\.?tech|mba|phd|ph\.d|bsc|msc|"
    r"b\.?sc|m\.?sc|engineering|science|arts|commerce|diploma|associate)\b",
    __import__("re").IGNORECASE,
)
_YEAR_RE = __import__("re").compile(r"\b(19|20)\d{2}\b")


def _score_resume_structured(profile: dict, optimized: dict) -> dict:
    """Deterministic rule-based scorer — inspects JSON directly, no AI calls.
    Uses identical thresholds to the optimizer prompt so 100/100 is achievable."""
    import re

    sections: dict = {}

    # ── contact_info (10) ───────────────────────────────────────────────────
    has_email = bool((profile.get("email") or "").strip())
    has_phone = bool((profile.get("phone") or "").strip())
    has_linkedin = bool(
        (profile.get("linkedin") or profile.get("linkedin_url") or "").strip()
    )
    has_github = bool(
        (
            profile.get("github_username")
            or profile.get("github")
            or profile.get("github_url")
            or ""
        ).strip()
    )
    present = sum([has_email, has_phone, has_linkedin, has_github])
    contact_score = {4: 10, 3: 7, 2: 5, 1: 2}.get(present, 0)
    contact_tips = (
        ([] if has_linkedin else ["Add LinkedIn URL"])
        + ([] if has_github else ["Add GitHub / portfolio URL"])
        + ([] if has_email else ["Add email address"])
        + ([] if has_phone else ["Add phone number"])
    )
    sections["contact_info"] = {"score": contact_score, "max": 10, "tips": contact_tips}

    # ── summary (10) ────────────────────────────────────────────────────────
    summary = str(optimized.get("summary") or "")
    words = len(summary.split())
    sentences = len([s for s in re.split(r"[.!?]+", summary) if s.strip()])
    metrics = len(_METRIC_RE.findall(summary))
    if sentences >= SUMMARY_MIN_SENTENCES_EXCELLENT and words >= SUMMARY_MIN_WORDS_EXCELLENT and metrics >= SUMMARY_MIN_METRICS_EXCELLENT:
        sum_score = SUMMARY_SCORE_EXCELLENT
    elif sentences >= SUMMARY_MIN_SENTENCES_GOOD and words >= SUMMARY_MIN_WORDS_GOOD and metrics >= SUMMARY_MIN_METRICS_GOOD:
        sum_score = SUMMARY_SCORE_GOOD
    else:
        sum_score = SUMMARY_SCORE_MIN
    sum_tips: list = []
    if words < SUMMARY_MIN_WORDS_EXCELLENT:
        sum_tips.append(f"Expand summary to {SUMMARY_MIN_WORDS_EXCELLENT}+ words (currently {words})")
    if metrics < SUMMARY_MIN_METRICS_EXCELLENT:
        sum_tips.append(f"Need {SUMMARY_MIN_METRICS_EXCELLENT}+ hard metrics in summary (found {metrics})")
    if sentences < SUMMARY_MIN_SENTENCES_EXCELLENT:
        sum_tips.append(f"Expand to {SUMMARY_MIN_SENTENCES_EXCELLENT}+ sentences (currently {sentences})")
    sections["summary"] = {"score": sum_score, "max": SUMMARY_SCORE_EXCELLENT, "tips": sum_tips}

    # ── skills ──────────────────────────────────────────────────────────────
    skills = optimized.get("skills") or {}
    all_skills = [
        s for group in skills.values() if isinstance(group, list) for s in group if s
    ]
    skill_count = len(all_skills)
    skills_score = (
        SKILLS_SCORE_EXCELLENT if skill_count >= SKILLS_COUNT_EXCELLENT
        else (SKILLS_SCORE_GOOD if skill_count >= SKILLS_COUNT_GOOD else SKILLS_SCORE_MIN)
    )
    skills_tips = (
        [] if skill_count >= SKILLS_COUNT_EXCELLENT
        else [f"Add {SKILLS_COUNT_EXCELLENT - skill_count} more named skills (currently {skill_count})"]
    )
    sections["skills"] = {"score": skills_score, "max": SKILLS_SCORE_EXCELLENT, "tips": skills_tips}

    # ── experience ──────────────────────────────────────────────────────────
    experience = optimized.get("experience") or []
    exp_tips: list = []
    if not experience:
        sections["experience"] = {"score": 0, "max": EXP_SCORE_EXCELLENT, "tips": ["No experience entries found"]}
    else:
        total_bullets = 0
        bullets_with_metric = 0
        bullets_with_verb = 0
        bullets_missing_metric: list = []
        for exp in experience:
            highlights = [h for h in (exp.get("highlights") or []) if isinstance(h, str)]
            total_bullets += len(highlights)
            if len(highlights) < BULLETS_PER_ROLE_TARGET:
                exp_tips.append(
                    f"'{exp.get('title', 'role')}' needs {BULLETS_PER_ROLE_TARGET - len(highlights)} more bullet(s) (has {len(highlights)}/{BULLETS_PER_ROLE_TARGET})"
                )
            for h in highlights:
                first = h.strip().split()[0].lower().rstrip(".,") if h.strip() else ""
                if first in _ACTION_VERBS:
                    bullets_with_verb += 1
                if _METRIC_RE.search(h):
                    bullets_with_metric += 1
                else:
                    bullets_missing_metric.append(f"[{exp.get('title', 'role')}] {h[:120]}")

        expected = len(experience) * BULLETS_PER_ROLE_TARGET
        bullet_ratio = total_bullets / expected if expected else 0
        metric_ratio = bullets_with_metric / total_bullets if total_bullets else 0

        if bullet_ratio >= EXP_BULLET_RATIO_EXCELLENT and metric_ratio >= EXP_METRIC_RATIO_EXCELLENT:
            exp_score = EXP_SCORE_EXCELLENT
        elif bullet_ratio >= EXP_BULLET_RATIO_GOOD and metric_ratio >= EXP_METRIC_RATIO_GOOD:
            exp_score = EXP_SCORE_GOOD
        else:
            exp_score = EXP_SCORE_MIN

        if bullets_missing_metric:
            exp_tips.append(
                f"These {len(bullets_missing_metric)} bullet(s) have no hard metric — "
                f"add a number (%, x, K+, ms, $, etc.) to each: "
                + " | ".join(bullets_missing_metric[:6])
            )
        sections["experience"] = {"score": exp_score, "max": EXP_SCORE_EXCELLENT, "tips": exp_tips}

    # ── education ───────────────────────────────────────────────────────────
    edu = str(profile.get("education") or "")
    has_degree = bool(_DEGREE_RE.search(edu))
    has_year = bool(_YEAR_RE.search(edu))
    edu_score = (
        EDUCATION_SCORE_COMPLETE if (edu and has_degree and has_year)
        else (EDUCATION_SCORE_PARTIAL if (edu and has_degree) else (EDUCATION_SCORE_MINIMAL if edu else 0))
    )
    edu_tips = (
        ([] if has_year or not edu else ["Add graduation year"])
        + ([] if has_degree or not edu else ["Add degree name"])
        + ([] if edu else ["Add education details"])
    )
    sections["education"] = {"score": edu_score, "max": EDUCATION_SCORE_COMPLETE, "tips": edu_tips}

    # ── formatting ──────────────────────────────────────────────────────────
    has_sum_sec = bool(optimized.get("summary"))
    has_skills_sec = bool(optimized.get("skills"))
    has_exp_sec = bool(optimized.get("experience"))
    bullets_clean = all(
        isinstance(h, str)
        for exp in (optimized.get("experience") or [])
        for h in (exp.get("highlights") or [])
    )
    fmt_score = (
        FORMAT_SCORE_COMPLETE if (has_sum_sec and has_skills_sec and has_exp_sec and bullets_clean)
        else (FORMAT_SCORE_PARTIAL if sum([has_sum_sec, has_skills_sec, has_exp_sec]) >= 2 else FORMAT_SCORE_MIN)
    )
    sections["formatting"] = {"score": fmt_score, "max": FORMAT_SCORE_COMPLETE, "tips": []}

    # ── ats_keywords ────────────────────────────────────────────────────────
    kws = [k for k in (optimized.get("ats_keywords") or []) if k]
    kw_count = len(kws)
    kw_score = (
        ATS_KW_SCORE_EXCELLENT if kw_count >= ATS_KW_COUNT_EXCELLENT
        else (ATS_KW_SCORE_GOOD if kw_count >= ATS_KW_COUNT_GOOD else ATS_KW_SCORE_MIN)
    )
    kw_tips = (
        [] if kw_count >= ATS_KW_COUNT_EXCELLENT
        else [f"Add {ATS_KW_COUNT_EXCELLENT - kw_count} more ATS keywords (currently {kw_count})"]
    )
    sections["ats_keywords"] = {"score": kw_score, "max": ATS_KW_SCORE_EXCELLENT, "tips": kw_tips}

    total = sum(s["score"] for s in sections.values())
    return {
        "total_score": total,
        "max_score": 100,
        "sections": sections,
        "method": "structured",
    }


def _reconstruct_and_score(
    profile: dict, optimized: dict, target_role: str = ""
) -> dict:
    """Score an optimized resume using a deterministic structural check.
    Directly inspects the JSON — no AI calls, no probabilistic drift, no subjective deductions.
    """
    return _score_resume_structured(profile, optimized)


@payment_bp.route("/optimize-resume", methods=["POST"])
@login_required
def optimize_resume():
    admin = is_admin(request.user)
    if not admin:
        db = _get_db()
        paid = db.payments.find_one(
            {
                "user_id": str(request.user["id"]),
                "status": "paid",
            }
        )
        if not paid:
            return jsonify({"error": "Payment required to use this feature"}), 402

    profile = get_user_profile(request.user)
    data = request.get_json() or {}
    target_role = data.get("target_role", profile.get("title", "Software Engineer"))
    target_company = data.get("target_company", "")
    job_description = data.get("job_description", "")

    skills_text = ", ".join(
        s for group in (profile.get("skills") or {}).values() for s in group
    )
    experience_text = ""
    for exp in profile.get("experience") or []:
        experience_text += f"\n{exp.get('title', '')} at {exp.get('company', '')} ({exp.get('period', '')})\n"
        for h in exp.get("highlights", []):
            experience_text += f"  - {h}\n"

    prompt = f"""You are a professional resume writer and ATS optimization expert.
Rewrite this candidate's resume to score 100/100 on ATS scanners for the target role.

SCORING RUBRIC — an independent AI will score your output on these exact criteria. Hit maximum in every section:
- contact_info (10/10): Must include email, phone, LinkedIn URL, GitHub/portfolio URL — all four present.
- summary (10/10): 4-5 sentences, 80+ words, 3+ quantified metrics, packed with role-specific ATS keywords.
- skills (15/15): 20+ specific named technologies across categories; every skill must be real and relevant to the target role.
- experience (25/25): EXACTLY 5 bullet points per role (no more, no less — ALL roles, not just the most recent); EVERY single bullet MUST contain a number (e.g. 40%, 10K+, 3x, 500ms, $2M, 5 engineers, 99.9% uptime). A bullet with no number at all scores zero for that bullet.
- education (10/10): Full degree name, institution name, and graduation year on separate detail lines.
- formatting (15/15): Consistent bullet style, clear section headers (SUMMARY, SKILLS, EXPERIENCE, EDUCATION, CERTIFICATIONS), no orphan lines.
- ats_keywords (15/15): 20+ role-specific ATS keywords naturally integrated throughout summary, skills, and bullets — NOT in a keyword dump.

ADDITIONAL RULES:
1. Preserve the candidate's actual tech stack. "Java" and "JavaScript" are DIFFERENT — never swap, merge, or confuse them.
2. Never fabricate companies, dates, degrees, or metrics the candidate does not have.
3. Keep all company names and periods exactly as provided.
4. Skills must be specific (e.g., "Spring Boot" not "Java frameworks", "PostgreSQL" not "databases").

TARGET ROLE: {target_role}
{"TARGET COMPANY: " + target_company if target_company else ""}
{"JOB DESCRIPTION:\n" + job_description[:3000] if job_description else ""}

CANDIDATE PROFILE:
Name: {profile.get('name', '')}
Current Title: {profile.get('title', '')}
Email: {profile.get('email', '')}
Phone: {profile.get('phone', '')}
Location: {profile.get('location', '')}
LinkedIn: {profile.get('linkedin', '') or profile.get('linkedin_url', '')}
GitHub: {profile.get('github', '') or profile.get('github_username', '')}
Years of Experience: {profile.get('years_of_experience', '')}
Skills: {skills_text}
Summary: {profile.get('summary', '')}
Education: {profile.get('education', '')}
Certifications: {', '.join(profile.get('certifications', []))}

EXPERIENCE:
{experience_text}

Return ONLY valid JSON (no markdown, no code fences):
{{
    "summary": "Rewritten professional summary (80+ words, 3+ metrics, role-keywords packed)",
    "skills": {{
        "languages": [...], "backend": [...], "frontend": [...],
        "databases": [...], "cloud_devops": [...], "architecture": [...], "testing": [...]
    }},
    "experience": [
        {{
            "title": "Optimized job title",
            "company": "Exact company name",
            "period": "Mon YYYY - Mon YYYY",
            "highlights": ["exactly 5 bullets, each with action verb + hard metric"]
        }}
    ],
    "certifications": ["list of certifications"],
    "ats_keywords": ["20+ ATS keywords used throughout"],
    "optimization_notes": ["what was improved and why"]
}}
"""

    try:
        from resume_parser import (
            _build_ai_providers,
            _call_ai_text,
            _is_quota_error,
            _parse_ai_response,
        )

        providers = _build_ai_providers()
        optimized = None

        for provider in providers:
            try:
                result_text = _call_ai_text(provider, prompt)
                parsed = _parse_ai_response(result_text)
                if parsed and "summary" in parsed:
                    optimized = _sanitize_optimized(parsed)
                    logger.info(f"Resume optimized with {provider['name']}")
                    break
            except Exception as e:
                if _is_quota_error(e):
                    continue
                logger.warning(f"Optimize failed ({provider['name']}): {e}")
                continue

        if not optimized:
            return (
                jsonify({"error": "All AI providers failed. Please try again later."}),
                500,
            )

        # Score and refine loop — keep improving until score = 100 or max passes reached.
        # Always refine from the BEST scored version to prevent AI-induced regressions.
        import copy as _copy
        import json as _json

        new_score = None
        best_score = 0
        best_optimized = _copy.deepcopy(optimized)

        for pass_num in range(1, MAX_OPTIMIZATION_PASSES + 1):
            try:
                new_score = _reconstruct_and_score(
                    profile, optimized, target_role=target_role
                )
            except Exception as score_err:
                logger.warning(f"Scoring failed on pass {pass_num}: {score_err}")
                # Restore best known good version and stop
                optimized = best_optimized
                new_score = None
                break

            current_total = new_score.get("total_score", 0)
            logger.info(f"Resume score after pass {pass_num}: {current_total}/100")

            # Track best — keep best version even if later passes regress
            if current_total > best_score:
                best_score = current_total
                best_optimized = _copy.deepcopy(optimized)
            else:
                # This pass regressed — revert to best for next refinement
                logger.info(
                    f"Pass {pass_num} regressed ({current_total} < {best_score}), reverting to best"
                )
                optimized = _copy.deepcopy(best_optimized)
                new_score["total_score"] = best_score  # report best score

            if best_score >= 100:
                break

            if pass_num >= MAX_OPTIMIZATION_PASSES:
                break

            section_gaps = []
            for section_name, section_data in new_score.get("sections", {}).items():
                if section_name not in REFINABLE_SECTIONS:
                    continue
                score = section_data.get("score", 0)
                max_val = section_data.get("max", 0)
                if score < max_val:
                    tips = section_data.get("tips", [])
                    tip_text = (
                        "; ".join(tips) if tips else "improve to meet ATS standards"
                    )
                    section_gaps.append(
                        f"- {section_name}: {score}/{max_val} — {tip_text}"
                    )

            if not section_gaps:
                break

            refinement_prompt = f"""You are a professional resume writer and ATS optimization expert.
This resume scored {best_score}/100 for the role: {target_role or "Software Engineer"}.
The ATS scoring AI identified these exact gaps — fix every one to reach 100/100.

SECTION GAPS (current score / max — what the scorer found wrong):
{chr(10).join(section_gaps)}

SCORING RUBRIC (what the scorer gives full marks for):
- contact_info 10/10: email + phone + LinkedIn URL + GitHub/portfolio URL all present
- summary 10/10: 4-5 sentences, 80+ words, 3+ hard metrics, role-specific keywords throughout
- skills 15/15: 20+ named technologies, organized by category, all specific and role-relevant
- experience 25/25: exactly 5 bullets per role, each bullet = action verb + hard quantified metric
- education 10/10: full degree name + institution + graduation year
- formatting 15/15: clear section headers, consistent bullets, professional structure
- ats_keywords 15/15: 20+ role-specific keywords woven naturally through summary, bullets, skills

CURRENT RESUME JSON (refine this — only fix the gap sections, preserve passing sections):
{_json.dumps(best_optimized, separators=(',', ':'))[:8000]}

CANDIDATE'S ACTUAL SKILLS: {skills_text}

Rules:
1. Fix every gap listed above — do not skip any.
2. Never fabricate companies, dates, or credentials the candidate does not have.
3. Never invent skills not in the candidate's actual skill set.
4. Return ONLY valid JSON in the exact same schema — no markdown, no code fences.
"""
            refined = None
            for provider in providers:
                try:
                    result_text = _call_ai_text(provider, refinement_prompt)
                    parsed = _parse_ai_response(result_text)
                    if parsed and "summary" in parsed:
                        refined = _sanitize_optimized(parsed)
                        logger.info(
                            f"Refinement pass {pass_num} succeeded with {provider['name']}"
                        )
                        break
                except Exception as e:
                    if _is_quota_error(e):
                        continue
                    logger.warning(
                        f"Refinement pass {pass_num} failed ({provider['name']}): {e}"
                    )
                    continue

            if refined:
                optimized = refined
            else:
                logger.warning(
                    f"Refinement pass {pass_num}: all providers failed, keeping best"
                )
                optimized = best_optimized
                break

        # Always return the best-scoring version
        optimized = best_optimized
        if new_score and new_score.get("total_score", 0) != best_score:
            new_score["total_score"] = best_score

        profile["optimized_resume"] = optimized
        profile["optimized_for"] = {
            "role": target_role,
            "company": target_company,
            "optimized_at": datetime.now(timezone.utc).isoformat(),
        }
        if new_score:
            profile["resume_score"] = new_score

        update_user_profile(request.user["id"], profile)

        if not admin:
            db.payments.update_one(
                {"_id": paid["_id"]},
                {
                    "$set": {
                        "status": "used",
                        "used_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

        return jsonify(
            {
                "message": "Resume optimized successfully!",
                "optimized": optimized,
                "resume_score": new_score,
                "profile": profile,
            }
        )
    except Exception as e:
        logger.error(f"Resume optimization failed: {e}")
        return jsonify({"error": f"Optimization failed: {str(e)}"}), 500


_ACCENT_COLORS = [
    "#2563eb",
    "#059669",
    "#7c3aed",
    "#b45309",
    "#0d9488",
    "#dc2626",
    "#6366f1",
    "#0284c7",
    "#16a34a",
    "#ea580c",
]

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "resume_templates"
)


@payment_bp.route("/download-resume-pdf", methods=["POST"])
@login_required
def download_resume_pdf():
    """Generate resume PDF server-side using WeasyPrint + HTML templates.
    Returns the PDF binary or 503 to signal the frontend to use its jsPDF fallback.
    """
    profile = get_user_profile(request.user)
    optimized = profile.get("optimized_resume")
    if not optimized:
        return (
            jsonify(
                {
                    "error": "No optimized resume found. Please optimize your resume first."
                }
            ),
            404,
        )

    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML

        template_files = [f for f in os.listdir(_TEMPLATES_DIR) if f.endswith(".html")]
        if not template_files:
            return jsonify({"error": "server_pdf_unavailable"}), 503

        env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
        template_file = random.choice(template_files)
        template = env.get_template(template_file)

        accent_color = random.choice(_ACCENT_COLORS)
        html_content = template.render(
            profile=profile, optimized=optimized, accent_color=accent_color
        )

        pdf_bytes = HTML(string=html_content, base_url=_TEMPLATES_DIR).write_pdf()

        safe_name = (profile.get("name") or "Resume").replace(" ", "_")
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_Resume.pdf"'
            },
        )

    except ImportError:
        logger.warning("WeasyPrint not installed — signalling frontend jsPDF fallback")
        return jsonify({"error": "server_pdf_unavailable"}), 503
    except Exception as e:
        logger.error(f"Server PDF generation failed: {e}")
        return jsonify({"error": "server_pdf_failed"}), 503
