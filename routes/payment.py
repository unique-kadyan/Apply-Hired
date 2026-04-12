"""Payment routes — Razorpay order creation, verification, and resume optimization."""

import logging
import os
import random
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from middleware import get_user_profile, is_admin, login_required
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
    custom_map = os.environ.get("COUNTRY_CURRENCY_MAP", "")
    mapping = {}
    if custom_map:
        for pair in custom_map.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                mapping[parts[0].strip().lower()] = parts[1].strip().upper()
    if not mapping:
        mapping = {
            "india": "INR",
            "usa": "USD",
            "united states": "USD",
            "uk": "GBP",
            "united kingdom": "GBP",
            "germany": "EUR",
            "france": "EUR",
            "spain": "EUR",
            "netherlands": "EUR",
            "ireland": "EUR",
            "europe": "EUR",
            "uae": "AED",
            "dubai": "AED",
            "singapore": "SGD",
            "australia": "AUD",
            "canada": "CAD",
            "japan": "JPY",
        }
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


def _reconstruct_and_score(profile: dict, optimized: dict) -> dict:
    """Score optimized resume directly from its structured JSON — no regex round-trip."""
    scores = {}
    total = 0

    # 1. Contact info (10 pts) — scored from profile fields directly
    contact_score = 0
    contact_tips = []
    if profile.get("email"):
        contact_score += 3
    else:
        contact_tips.append("Add your email address")
    if profile.get("phone"):
        contact_score += 3
    else:
        contact_tips.append("Add your phone number")
    has_linkedin = bool(profile.get("linkedin") or profile.get("linkedin_url"))
    has_github = bool(
        profile.get("github_username") or profile.get("github") or profile.get("github_url")
    )
    if has_linkedin:
        contact_score += 2
    else:
        contact_tips.append("Add your LinkedIn profile URL")
    if has_github:
        contact_score += 2
    else:
        contact_tips.append("Add your GitHub profile URL")
    scores["contact_info"] = {"score": contact_score, "max": 10, "tips": contact_tips}
    total += contact_score

    # 2. Summary (10 pts) — scored from optimized summary string
    summary_text = optimized.get("summary", "")
    summary_words = len(summary_text.split()) if summary_text else 0
    if summary_words >= 30:
        summary_score = 10
    elif summary_words >= 15:
        summary_score = 7
    elif summary_words > 0:
        summary_score = 4
    else:
        summary_score = 0
    summary_tips = []
    if summary_score < 10:
        if not summary_text:
            summary_tips.append("Add a professional summary at the top of your resume")
        else:
            summary_tips.append("Expand your summary to 2-3 sentences with measurable impact")
    scores["summary"] = {"score": summary_score, "max": 10, "tips": summary_tips}
    total += summary_score

    # 3. Skills (15 pts) — scored from optimized skills dict
    skills_dict = optimized.get("skills", {})
    skill_count = sum(len(v) for v in skills_dict.values() if isinstance(v, list))
    skill_score = min(15, round(skill_count * 1.5))
    skill_tips = []
    if skill_score < 15:
        skill_tips.append(f"Found {skill_count} skills — aim for 10+ relevant technical skills")
    scores["skills"] = {"score": skill_score, "max": 15, "tips": skill_tips}
    total += skill_score

    # 4. Experience (25 pts) — scored from optimized experience list
    experience_list = optimized.get("experience", [])
    exp_score = 0
    exp_tips = []
    if experience_list:
        role_count = len(experience_list)
        exp_score += min(10, role_count * 3)
        all_highlights = [h for exp in experience_list for h in exp.get("highlights", [])]
        bullet_count = len(all_highlights)
        exp_score += min(10, bullet_count * 2)
        highlights_text = " ".join(all_highlights)
        metrics = len(re.findall(
            r'\d+[%xX]|\$[\d,]+|\d+\+?\s*(?:users|clients|engineers|teams|rps)',
            highlights_text,
            re.IGNORECASE,
        ))
        exp_score += min(5, round(metrics * 1.5))
        if bullet_count < 6:
            exp_tips.append("Add more bullet points to each role (3-5 per job)")
        if metrics < 3:
            exp_tips.append("Quantify achievements with numbers (%, $, users, etc.)")
    else:
        exp_tips.append("Add your work experience with company names and dates")
    exp_score = min(25, exp_score)
    scores["experience"] = {"score": exp_score, "max": 25, "tips": exp_tips}
    total += exp_score

    # 5. Education (10 pts) — scored from profile education field
    edu_text = profile.get("education", "") or ""
    edu_score = 10 if len(edu_text.strip()) > 10 else 0
    edu_tips = [] if edu_score else ["Add your education with degree, university, and year"]
    scores["education"] = {"score": edu_score, "max": 10, "tips": edu_tips}
    total += edu_score

    # 6. Formatting & length (15 pts) — computed from structured content
    all_text_parts = [summary_text]
    for exp in experience_list:
        all_text_parts += exp.get("highlights", [])
    for v in skills_dict.values():
        if isinstance(v, list):
            all_text_parts += v
    full_text = " ".join(all_text_parts)
    word_count = len(full_text.split())
    format_score = 0
    if 300 <= word_count <= 1200:
        format_score += 5
    elif word_count > 100:
        format_score += 3
    total_bullets = sum(len(e.get("highlights", [])) for e in experience_list)
    if total_bullets >= 5:
        format_score += 5
    if experience_list and skills_dict and summary_text:
        format_score += 5
    format_tips = []
    if format_score < 15:
        if word_count < 300:
            format_tips.append("Resume seems too short — aim for 400-800 words")
        if total_bullets < 5:
            format_tips.append("Use bullet points for achievements instead of paragraphs")
    scores["formatting"] = {"score": min(15, format_score), "max": 15, "tips": format_tips}
    total += min(15, format_score)

    # 7. Keywords & ATS (15 pts) — checked across all text in optimized JSON
    ats_text = " ".join([
        summary_text,
        " ".join(str(v) for v in skills_dict.values()),
        " ".join(h for exp in experience_list for h in exp.get("highlights", [])),
        " ".join(
            f"{exp.get('title', '')} {exp.get('company', '')}" for exp in experience_list
        ),
    ])
    ats_keywords = [
        "team", "lead", "manage", "develop", "design", "implement", "optimize",
        "deploy", "scale", "architect", "mentor", "collaborate", "deliver", "automate",
    ]
    keyword_hits = sum(1 for kw in ats_keywords if re.search(rf"\b{kw}", ats_text, re.IGNORECASE))
    ats_score = min(15, keyword_hits * 2)
    ats_tips = []
    if ats_score < 15:
        ats_tips.append("Use action verbs: led, built, optimized, delivered, scaled, automated")
    scores["ats_keywords"] = {"score": round(ats_score), "max": 15, "tips": ats_tips}
    total += ats_score

    return {
        "total_score": round(min(100, total)),
        "max_score": 100,
        "sections": scores,
        "method": "optimized",
    }


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

RULES — follow every one:
1. Preserve the candidate's actual tech stack. "Java" and "JavaScript" are DIFFERENT — never swap, merge, or confuse them. Only list skills the candidate actually has.
2. Summary must be 3-4 sentences, 60+ words, packed with measurable impact and keywords for the target role.
3. Each experience entry must have EXACTLY 5 bullet points. Every bullet must start with a strong action verb and include at least one quantified metric (%, x faster, K+ users, $, ms latency, etc.).
4. Mandatory action verbs — use at least 10 of these across all bullets: led, built, optimized, deployed, scaled, designed, implemented, developed, collaborated, delivered, automated, architected, mentored, managed.
5. Skills section must contain 15+ skills across all categories. Be specific (e.g. "Spring Boot" not just "Java frameworks").
6. Keep all company names and periods exactly as provided — do not invent or alter them.

TARGET ROLE: {target_role}
{"TARGET COMPANY: " + target_company if target_company else ""}
{"JOB DESCRIPTION:\n" + job_description[:3000] if job_description else ""}

CANDIDATE PROFILE:
Name: {profile.get('name', '')}
Current Title: {profile.get('title', '')}
Email: {profile.get('email', '')}
Phone: {profile.get('phone', '')}
Location: {profile.get('location', '')}
Years of Experience: {profile.get('years_of_experience', '')}
Skills: {skills_text}
Summary: {profile.get('summary', '')}
Education: {profile.get('education', '')}
Certifications: {', '.join(profile.get('certifications', []))}

EXPERIENCE:
{experience_text}

Return ONLY valid JSON (no markdown, no code fences):
{{
    "summary": "Rewritten professional summary (60+ words, metrics-packed)",
    "skills": {{
        "languages": [...], "backend": [...], "frontend": [...],
        "databases": [...], "cloud_devops": [...], "architecture": [...], "testing": [...]
    }},
    "experience": [
        {{
            "title": "Optimized job title",
            "company": "Exact company name",
            "period": "Mon YYYY - Mon YYYY",
            "highlights": ["5 ATS-optimized bullets each with action verb + metric"]
        }}
    ],
    "ats_keywords": ["list of ATS keywords used"],
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
                    optimized = parsed
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

        profile["optimized_resume"] = optimized
        profile["optimized_for"] = {
            "role": target_role,
            "company": target_company,
            "optimized_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            new_score = _reconstruct_and_score(profile, optimized)
            profile["resume_score"] = new_score
        except Exception as score_err:
            logger.warning(f"Post-optimization scoring failed: {score_err}")
            new_score = None

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
    "#2563eb", "#059669", "#7c3aed", "#b45309", "#0d9488",
    "#dc2626", "#6366f1", "#0284c7", "#16a34a", "#ea580c",
]

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resume_templates")


@payment_bp.route("/download-resume-pdf", methods=["POST"])
@login_required
def download_resume_pdf():
    """Generate resume PDF server-side using WeasyPrint + HTML templates.
    Returns the PDF binary or 503 to signal the frontend to use its jsPDF fallback.
    """
    profile = get_user_profile(request.user)
    optimized = profile.get("optimized_resume")
    if not optimized:
        return jsonify({"error": "No optimized resume found. Please optimize your resume first."}), 404

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
        html_content = template.render(profile=profile, optimized=optimized, accent_color=accent_color)

        pdf_bytes = HTML(string=html_content, base_url=_TEMPLATES_DIR).write_pdf()

        safe_name = (profile.get("name") or "Resume").replace(" ", "_")
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_Resume.pdf"'},
        )

    except ImportError:
        logger.warning("WeasyPrint not installed — signalling frontend jsPDF fallback")
        return jsonify({"error": "server_pdf_unavailable"}), 503
    except Exception as e:
        logger.error(f"Server PDF generation failed: {e}")
        return jsonify({"error": "server_pdf_failed"}), 503
