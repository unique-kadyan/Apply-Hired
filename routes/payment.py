"""Payment routes — Razorpay order creation, verification, and resume optimization."""

import logging
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from middleware import get_user_profile, login_required
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
    "INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3",
    "AED": "AED ", "SGD": "S$", "AUD": "A$", "CAD": "C$",
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
        resp = req.get(f"https://api.exchangerate-api.com/v4/latest/{_BASE_CURRENCY}", timeout=5)
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
            "india": "INR", "usa": "USD", "united states": "USD",
            "uk": "GBP", "united kingdom": "GBP",
            "germany": "EUR", "france": "EUR", "spain": "EUR",
            "netherlands": "EUR", "ireland": "EUR",
            "europe": "EUR", "uae": "AED", "dubai": "AED",
            "singapore": "SGD", "australia": "AUD", "canada": "CAD",
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
            "currency": currency, "symbol": symbol,
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
        "currency": currency, "symbol": symbol,
        "display_amount": f"{symbol}{converted}",
        "razorpay_amount": round(_BASE_PRICE * _INTL_MARKUP * 100) if currency != _BASE_CURRENCY else _BASE_PRICE * 100,
    }

@payment_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    profile = get_user_profile(request.user)
    currency = _get_user_currency(profile)
    price = _calculate_price(currency)
    return jsonify({
        "key_id": _key_id(),
        "amount": price["razorpay_amount"],
        "currency": "INR",
        "user_currency": currency,
        "display_amount": price["display_amount"],
        "configured": is_configured(),
    })

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
        db.payments.insert_one({
            "user_id": str(request.user["id"]),
            "order_id": order["id"],
            "amount": price["razorpay_amount"],
            "display_amount": price["display_amount"],
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": _key_id(),
        })
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
        {"$set": {
            "payment_id": payment_id,
            "signature": signature,
            "status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return jsonify({"message": "Payment verified", "paid": True})

@payment_bp.route("/has-paid", methods=["GET"])
@login_required
def has_paid():
    db = _get_db()
    paid = db.payments.find_one({
        "user_id": str(request.user["id"]),
        "status": "paid",
    })
    return jsonify({"paid": bool(paid)})

@payment_bp.route("/optimize-resume", methods=["POST"])
@login_required
def optimize_resume():
    db = _get_db()
    paid = db.payments.find_one({
        "user_id": str(request.user["id"]),
        "status": "paid",
    })
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
    for exp in (profile.get("experience") or []):
        experience_text += f"\n{exp.get('title', '')} at {exp.get('company', '')} ({exp.get('period', '')})\n"
        for h in exp.get("highlights", []):
            experience_text += f"  - {h}\n"

    prompt = f"""You are a professional resume writer and ATS optimization expert.

Rewrite this candidate's resume to be FULLY ATS-optimized and tailored for the target role.

IMPORTANT: Preserve the candidate's actual tech stack accurately. "Java" and "JavaScript" are different — do not swap, merge, or confuse them. Only include skills the candidate actually has. Do not add skills not present in their profile.

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

Return ONLY valid JSON:
{{
    "summary": "Rewritten professional summary",
    "skills": {{
        "languages": [...], "backend": [...], "frontend": [...],
        "databases": [...], "cloud_devops": [...], "architecture": [...], "testing": [...]
    }},
    "experience": [
        {{
            "title": "Optimized job title",
            "company": "Company Name",
            "period": "Mon YYYY - Mon YYYY",
            "highlights": ["ATS-optimized bullet 1", "bullet 2"]
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
            return jsonify({"error": "All AI providers failed. Please try again later."}), 500

        profile["optimized_resume"] = optimized
        profile["optimized_for"] = {
            "role": target_role,
            "company": target_company,
            "optimized_at": datetime.now(timezone.utc).isoformat(),
        }
        update_user_profile(request.user["id"], profile)

        db.payments.update_one(
            {"_id": paid["_id"]},
            {"$set": {"status": "used", "used_at": datetime.now(timezone.utc).isoformat()}},
        )

        return jsonify({
            "message": "Resume optimized successfully!",
            "optimized": optimized,
            "profile": profile,
        })
    except Exception as e:
        logger.error(f"Resume optimization failed: {e}")
        return jsonify({"error": f"Optimization failed: {str(e)}"}), 500
