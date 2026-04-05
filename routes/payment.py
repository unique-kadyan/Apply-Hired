"""Payment routes — Razorpay order creation, verification, and resume optimization."""

import os
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from middleware import login_required, get_user_profile
from services.payment_service import (
    is_configured, create_order, verify_payment,
    _key_id, RESUME_OPTIMIZE_PRICE,
)
from tracker import _get_db, update_user_profile

logger = logging.getLogger(__name__)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/payment")

# All pricing config from env
_BASE_PRICE = int(os.environ.get("RESUME_PRICE_INR", 50))
_INTL_MARKUP = float(os.environ.get("INTL_MARKUP_PERCENT", 30)) / 100 + 1  # e.g. 30 → 1.30
_BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "INR")

# Currency symbols (lightweight, no rates needed — fetched live)
_SYMBOLS = {
    "INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3",
    "AED": "AED ", "SGD": "S$", "AUD": "A$", "CAD": "C$",
    "JPY": "\u00a5", "BRL": "R$", "CHF": "CHF ", "SEK": "kr",
    "MYR": "RM", "KRW": "\u20a9", "THB": "\u0e3f", "IDR": "Rp",
    "PHP": "\u20b1", "NZD": "NZ$", "ZAR": "R", "HKD": "HK$",
}

# Cache for exchange rates (refreshed every hour)
_rate_cache = {"rates": {}, "fetched_at": 0}


def _fetch_exchange_rates() -> dict:
    """Fetch live exchange rates from a free API. Cached for 1 hour."""
    import time
    now = time.time()
    if _rate_cache["rates"] and now - _rate_cache["fetched_at"] < 3600:
        return _rate_cache["rates"]

    try:
        import requests as req
        # Free, no key needed, 1500 req/month
        resp = req.get(
            f"https://api.exchangerate-api.com/v4/latest/{_BASE_CURRENCY}",
            timeout=5,
        )
        data = resp.json()
        _rate_cache["rates"] = data.get("rates", {})
        _rate_cache["fetched_at"] = now
        return _rate_cache["rates"]
    except Exception as e:
        logger.warning(f"Exchange rate fetch failed: {e}")
        return _rate_cache.get("rates", {})


def _get_user_currency(user_profile: dict) -> str:
    """Detect currency from user's location using env-configurable mapping."""
    location = (user_profile.get("location") or "").lower()

    # Load custom mapping from env: "india:INR,usa:USD,uk:GBP,..."
    custom_map = os.environ.get("COUNTRY_CURRENCY_MAP", "")
    mapping = {}
    if custom_map:
        for pair in custom_map.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                mapping[parts[0].strip().lower()] = parts[1].strip().upper()

    # Default mapping if env not set
    if not mapping:
        mapping = {
            "india": "INR", "usa": "USD", "united states": "USD",
            "uk": "GBP", "united kingdom": "GBP", "england": "GBP",
            "germany": "EUR", "france": "EUR", "spain": "EUR",
            "netherlands": "EUR", "ireland": "EUR", "italy": "EUR",
            "europe": "EUR", "uae": "AED", "dubai": "AED",
            "singapore": "SGD", "australia": "AUD", "canada": "CAD",
            "japan": "JPY", "brazil": "BRL", "switzerland": "CHF",
            "sweden": "SEK", "south korea": "KRW", "malaysia": "MYR",
            "thailand": "THB", "indonesia": "IDR", "philippines": "PHP",
            "new zealand": "NZD", "south africa": "ZAR", "hong kong": "HKD",
        }

    for keyword, currency in mapping.items():
        if keyword in location:
            return currency
    return _BASE_CURRENCY


def _calculate_price(currency: str) -> dict:
    """Calculate price in the user's currency using live exchange rates."""
    symbol = _SYMBOLS.get(currency, currency + " ")

    if currency == _BASE_CURRENCY:
        return {
            "currency": currency,
            "symbol": symbol,
            "display_amount": f"{symbol}{_BASE_PRICE}",
            "razorpay_amount": _BASE_PRICE * 100,  # paise
        }

    # Fetch live rate and apply international markup
    rates = _fetch_exchange_rates()
    rate = rates.get(currency, 0)

    if rate > 0:
        converted = _BASE_PRICE * rate * _INTL_MARKUP
        # Clean rounding
        if converted >= 100:
            converted = round(converted)
        elif converted >= 1:
            converted = round(converted, 1)
        else:
            converted = round(converted, 2)
    else:
        # Fallback: just show base price with markup in base currency
        converted = round(_BASE_PRICE * _INTL_MARKUP)
        currency = _BASE_CURRENCY
        symbol = _SYMBOLS.get(_BASE_CURRENCY, "")

    # Razorpay always charges in base currency (INR paise)
    razorpay_amount = round(_BASE_PRICE * _INTL_MARKUP * 100)

    return {
        "currency": currency,
        "symbol": symbol,
        "display_amount": f"{symbol}{converted}",
        "razorpay_amount": razorpay_amount,
    }


@payment_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    """Return Razorpay public key and price based on user's location."""
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
    """Create a Razorpay order for resume optimization."""
    if not is_configured():
        return jsonify({"error": "Payment gateway not configured"}), 500

    try:
        profile = get_user_profile(request.user)
        currency = _get_user_currency(profile)
        price = _calculate_price(currency)

        order = create_order(
            amount_paise=price["razorpay_amount"],
            receipt=f"resume_{request.user['id']}_{int(datetime.now().timestamp())}",
        )
        # Store order in DB
        db = _get_db()
        db.payments.insert_one({
            "user_id": str(request.user["id"]),
            "order_id": order["id"],
            "amount": price["razorpay_amount"],
            "user_currency": currency,
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
    """Verify Razorpay payment and unlock resume optimization."""
    data = request.get_json() or {}
    order_id = data.get("order_id", "")
    payment_id = data.get("payment_id", "")
    signature = data.get("signature", "")

    if not order_id or not payment_id or not signature:
        return jsonify({"error": "Missing payment details"}), 400

    # Verify signature
    if not verify_payment(order_id, payment_id, signature):
        return jsonify({"error": "Payment verification failed"}), 400

    # Update payment record
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
    """Check if user has an active paid resume optimization."""
    db = _get_db()
    paid = db.payments.find_one({
        "user_id": str(request.user["id"]),
        "status": "paid",
    })
    return jsonify({"paid": bool(paid)})


@payment_bp.route("/optimize-resume", methods=["POST"])
@login_required
def optimize_resume():
    """Generate an ATS-optimized, job-tailored resume using AI. Requires payment."""
    # Check payment
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

    # Build the AI prompt
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

INSTRUCTIONS:
1. Write a powerful PROFESSIONAL SUMMARY (3-4 sentences) with metrics and keywords matching the target role
2. Rewrite EACH job experience with:
   - Strong action verbs (Led, Architected, Optimized, Delivered, Scaled)
   - Quantified achievements (%, $, users, RPS, uptime numbers)
   - Keywords from the job description woven naturally
   - 3-5 bullet points per role, ordered by impact
3. Organize SKILLS into clear categories, prioritizing those relevant to the target role
4. Ensure ATS compatibility:
   - No tables, columns, or graphics references
   - Standard section headers
   - Consistent date formatting
   - Keywords from the job description appear naturally
5. Keep it to 1-2 pages worth of content

Return ONLY valid JSON:
{{
    "summary": "Rewritten professional summary",
    "skills": {{
        "languages": [...],
        "backend": [...],
        "frontend": [...],
        "databases": [...],
        "cloud_devops": [...],
        "architecture": [...],
        "testing": [...]
    }},
    "experience": [
        {{
            "title": "Optimized job title",
            "company": "Company Name",
            "period": "Mon YYYY - Mon YYYY",
            "highlights": ["ATS-optimized bullet 1", "bullet 2", ...]
        }}
    ],
    "ats_keywords": ["list of ATS keywords used"],
    "optimization_notes": ["what was improved and why"]
}}
"""

    try:
        from resume_parser import _build_ai_providers, _call_ai_text, _parse_ai_response, _is_quota_error

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

        # Save optimized version to profile
        profile["optimized_resume"] = optimized
        profile["optimized_for"] = {
            "role": target_role,
            "company": target_company,
            "optimized_at": datetime.now(timezone.utc).isoformat(),
        }
        update_user_profile(request.user["id"], profile)

        # Mark payment as used
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
