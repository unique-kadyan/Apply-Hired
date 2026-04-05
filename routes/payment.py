"""Payment routes — Razorpay order creation, verification, and resume optimization."""

import os
import re
import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from config import OPENAI_API_KEY
from middleware import login_required, get_user_profile
from services.payment_service import (
    is_configured, create_order, verify_payment,
    _key_id, RESUME_OPTIMIZE_PRICE,
)
from tracker import _get_db, update_user_profile

logger = logging.getLogger(__name__)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/payment")


@payment_bp.route("/config", methods=["GET"])
@login_required
def get_config():
    """Return Razorpay public key and price for the frontend."""
    return jsonify({
        "key_id": _key_id(),
        "amount": RESUME_OPTIMIZE_PRICE,
        "currency": "INR",
        "display_amount": f"\u20b9{RESUME_OPTIMIZE_PRICE // 100}",
        "configured": is_configured(),
    })


@payment_bp.route("/create-order", methods=["POST"])
@login_required
def create_payment_order():
    """Create a Razorpay order for resume optimization."""
    if not is_configured():
        return jsonify({"error": "Payment gateway not configured"}), 500

    try:
        order = create_order(
            amount_paise=RESUME_OPTIMIZE_PRICE,
            receipt=f"resume_{request.user['id']}_{int(datetime.now().timestamp())}",
        )
        # Store order in DB
        db = _get_db()
        db.payments.insert_one({
            "user_id": str(request.user["id"]),
            "order_id": order["id"],
            "amount": RESUME_OPTIMIZE_PRICE,
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

    if not OPENAI_API_KEY:
        return jsonify({"error": "AI service not available"}), 500

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
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        result_text = response.choices[0].message.content
        json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if not json_match:
            return jsonify({"error": "AI returned invalid response"}), 500

        optimized = json.loads(json_match.group())

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
