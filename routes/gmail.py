"""Gmail API integration — auto-detect interview invitations and offer letters."""

import base64
import logging
import os
import re
import secrets
from datetime import datetime
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, jsonify, redirect, request, session

from middleware import login_required
from tracker import _get_db, _to_object_id

logger = logging.getLogger(__name__)

gmail_bp = Blueprint("gmail", __name__, url_prefix="/api/gmail")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# ---------------------------------------------------------------------------
# Email classification keywords
# ---------------------------------------------------------------------------

# Phrases that strongly indicate an interview invitation
_INTERVIEW_PHRASES = [
    "invitation to interview",
    "invite you for an interview",
    "scheduled for an interview",
    "selected for interview",
    "interview invitation",
    "interview schedule",
    "we would like to interview",
    "pleased to invite you",
    "next round",
    "technical interview",
    "hr interview",
    "coding round",
    "technical round",
    "interview details",
    "please join us for",
    "meeting scheduled",
]

# Phrases that strongly indicate an offer letter
_OFFER_PHRASES = [
    "offer letter",
    "offer of employment",
    "pleased to offer",
    "job offer",
    "employment offer",
    "formal offer",
    "offer you the position",
    "pleased to extend an offer",
    "offer of the position",
    "we are delighted to offer",
    "congratulations on your offer",
    "joining date",
    "date of joining",
    "compensation package",
    "annual ctc",
    "cost to company",
    "welcome to the team",
]

# Weaker signals used for scoring when strong phrases not found
_INTERVIEW_WEAK = ["interview", "round", "schedule", "zoom", "google meet", "teams"]
_OFFER_WEAK = [
    "offer",
    "salary",
    "compensation",
    "ctc",
    "lpa",
    "joining",
    "congratulations",
]

# Email domains to ignore when extracting company name
_GENERIC_DOMAINS = {
    "gmail",
    "yahoo",
    "hotmail",
    "outlook",
    "live",
    "icloud",
    "zoho",
    "protonmail",
    "rediff",
    "aol",
    "mail",
    "noreply",
    "notifications",
    "jobs",
    "careers",
    "recruiting",
    "no-reply",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_gmail_callback_url() -> str:
    """Build Gmail callback URL dynamically, matching the actual request domain."""
    url = request.url_root.rstrip("/") + "/api/gmail/callback"
    # Force HTTPS for non-localhost production environments
    if url.startswith("http://") and "localhost" not in url and "127.0.0.1" not in url:
        url = url.replace("http://", "https://", 1)
    return url


def _refresh_access_token(refresh_token: str) -> str | None:
    try:
        resp = http_requests.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        return resp.json().get("access_token")
    except Exception as e:
        logger.warning(f"Gmail token refresh failed: {e}")
        return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_body(payload: dict, depth: int = 0) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    if depth > 5:
        return ""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        return _decode_body(payload.get("body", {}).get("data", ""))
    if mime.startswith("multipart"):
        return " ".join(_extract_body(p, depth + 1) for p in payload.get("parts", []))
    return ""


def _classify_email(subject: str, body: str) -> str | None:
    """
    Classify an email as 'interview', 'offer', or None.
    Uses strong phrases first, falls back to weak-signal scoring.
    """
    text = f"{subject} {body}".lower()

    # Strong phrase match wins immediately
    for phrase in _OFFER_PHRASES:
        if phrase in text:
            return "offer"
    for phrase in _INTERVIEW_PHRASES:
        if phrase in text:
            return "interview"

    # Weak scoring fallback
    offer_score = sum(1 for kw in _OFFER_WEAK if kw in text)
    int_score = sum(1 for kw in _INTERVIEW_WEAK if kw in text)

    if offer_score >= 3:
        return "offer"
    if int_score >= 3:
        return "interview"
    return None


def _extract_interview_details(subject: str, body: str, email_date: str) -> dict:
    """
    Parse interview-specific details from email body using regex patterns.
    Covers common formats used by Indian and global HR/ATS emails.
    """
    text = f"{subject}\n{body}"

    details: dict = {
        "notes": f"Auto-detected from Gmail — {subject[:100]}",
        "saved_at": datetime.now().isoformat(),
    }

    # ── Date ──────────────────────────────────────────────────────────────────
    # Matches: "on 15th April 2026", "on April 15, 2026", "on 15/04/2026",
    #          "on Monday, 15 April", "scheduled for April 15"
    date_patterns = [
        r"(?:on|for|date[:\s]+)\s*(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\,?\s*"
        r"(\d{1,2}(?:st|nd|rd|th)?[\s\-/]+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s\-/,]+(?:20\d{2}))",
        r"(\d{1,2}[/\-]\d{1,2}[/\-](?:20)?\d{2})",
        r"((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
        r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2})",
    ]
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            details["date"] = m.group(1).strip()
            break

    # ── Time ──────────────────────────────────────────────────────────────────
    # Matches: "at 2:30 PM", "at 14:30", "at 10 AM IST"
    time_m = re.search(
        r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b(?:\s*(ist|gmt|utc[+\-]?\d*|pst|est|cst|mst))?",
        text,
        re.IGNORECASE,
    )
    if time_m:
        details["time"] = time_m.group(1).strip()
        if time_m.group(2):
            details["timezone"] = time_m.group(2).upper()

    # ── Timezone standalone ────────────────────────────────────────────────────
    if "timezone" not in details:
        tz_m = re.search(
            r"\b(IST|GMT[+\-]?\d*|UTC[+\-]?\d*|PST|EST|CST|MST|AEST|CET|BST)\b", text
        )
        if tz_m:
            details["timezone"] = tz_m.group(1)

    # ── Round / Stage ──────────────────────────────────────────────────────────
    round_m = re.search(
        r"((?:hr|technical|coding|system design|behavioral|managerial|final|panel|"
        r"screening|phone|video|round\s*\d+|round\s+[a-z]+)\s+(?:round|interview|screen|call)?)",
        text,
        re.IGNORECASE,
    )
    if round_m:
        details["round"] = round_m.group(1).strip().title()

    # ── Meeting / Video call link ──────────────────────────────────────────────
    link_m = re.search(
        r"(https?://(?:meet\.google\.com|zoom\.us/j|teams\.microsoft\.com|"
        r"webex\.com|whereby\.com|meet\.jit\.si)[^\s\"<>]+)",
        text,
        re.IGNORECASE,
    )
    if link_m:
        details["meeting_link"] = link_m.group(1)

    # ── Platform from link or mention ─────────────────────────────────────────
    if "meeting_link" in details:
        link_lower = details["meeting_link"].lower()
        if "zoom" in link_lower:
            details["platform"] = "Zoom"
        elif "meet.google" in link_lower:
            details["platform"] = "Google Meet"
        elif "teams" in link_lower:
            details["platform"] = "Microsoft Teams"
        elif "webex" in link_lower:
            details["platform"] = "Webex"
    else:
        for platform in ["Zoom", "Google Meet", "Microsoft Teams", "Webex", "Whereby"]:
            if platform.lower() in text.lower():
                details["platform"] = platform
                break

    # ── Interviewer name ──────────────────────────────────────────────────────
    interviewer_m = re.search(
        r"(?:with|interviewer[:\s]+|conducted by[:\s]+|meet\s+(?:with\s+)?|"
        r"your\s+interviewer\s+(?:is|will be)\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
        text,
    )
    if interviewer_m:
        name = interviewer_m.group(1).strip()
        # Filter out generic words that look like names
        if name.lower() not in {"the team", "our team", "hr team", "recruiter"}:
            details["interviewer"] = name

    return details


def _extract_offer_details(subject: str, body: str) -> dict:
    """
    Parse offer-specific details from email body.
    Extracts CTC/salary, joining date, deadline, benefits, location.
    """
    text = f"{subject}\n{body}"

    details: dict = {
        "notes": f"Auto-detected from Gmail — {subject[:100]}",
        "saved_at": datetime.now().isoformat(),
    }

    # ── Salary / CTC ──────────────────────────────────────────────────────────
    # Matches: "₹25 LPA", "25 LPA", "$120,000", "INR 25,00,000", "CTC of ₹18 LPA"
    salary_patterns = [
        r"(?:ctc|salary|compensation|package|offer)[^\n]{0,30}?((?:₹|inr|rs\.?|usd|\$|£|eur|€)\s*[\d,]+(?:\.\d+)?(?:\s*(?:lpa|lakh|lac|k|thousand|million|per annum|per year|pa|annually))?)",
        r"((?:₹|inr|rs\.?|usd|\$|£|eur|€)\s*[\d,]+(?:\.\d+)?\s*(?:lpa|lakh|lac|k|thousand|million|per annum|per year|pa)?)",
        r"(\d+(?:\.\d+)?\s*(?:lpa|lakh per annum|lacs per annum))",
    ]
    for pat in salary_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            details["salary"] = m.group(1).strip()
            break

    # ── Currency detection ─────────────────────────────────────────────────────
    if "salary" in details:
        s = details["salary"].lower()
        if any(c in s for c in ["₹", "inr", "rs", "lpa", "lakh"]):
            details["currency"] = "INR"
        elif any(c in s for c in ["$", "usd"]):
            details["currency"] = "USD"
        elif "£" in s or "gbp" in s:
            details["currency"] = "GBP"
        elif "€" in s or "eur" in s:
            details["currency"] = "EUR"

    # ── Joining date ──────────────────────────────────────────────────────────
    join_m = re.search(
        r"(?:joining date|date of joining|start date|joining on|commence)[:\s]*"
        r"((?:monday|tuesday|wednesday|thursday|friday)?\,?\s*"
        r"\d{1,2}(?:st|nd|rd|th)?[\s\-/]+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"[\s\-/,]+(?:20\d{2})?|\d{1,2}[/\-]\d{1,2}[/\-](?:20)?\d{2})",
        text,
        re.IGNORECASE,
    )
    if join_m:
        details["joining_date"] = join_m.group(1).strip()

    # ── Acceptance deadline ────────────────────────────────────────────────────
    deadline_m = re.search(
        r"(?:accept(?:ance)?|respond|revert|reply)\s+(?:by|before|within)[:\s]+"
        r"((?:\d{1,2}[\s\-/]+(?:jan(?:uary)?|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"
        r"[\s\-/]*(?:20\d{2})?|\d{1,2}[/\-]\d{1,2}[/\-](?:20)?\d{2}|\d+\s+(?:business\s+)?days?))",
        text,
        re.IGNORECASE,
    )
    if deadline_m:
        details["deadline"] = deadline_m.group(1).strip()

    # ── Work location ──────────────────────────────────────────────────────────
    location_m = re.search(
        r"(?:work\s+(?:location|from)|location|office|based\s+(?:out\s+of|in))[:\s]+"
        r"((?:remote|hybrid|work from home|wfh|on.?site|bengaluru|bangalore|mumbai|delhi|"
        r"hyderabad|chennai|pune|noida|gurgaon|gurugram|[a-z\s]{3,30}))",
        text,
        re.IGNORECASE,
    )
    if location_m:
        details["location"] = location_m.group(1).strip().title()

    # ── Benefits snippet (grab the sentence mentioning benefits/perks) ─────────
    benefits_m = re.search(
        r"(?:benefits?|perks?|includes?)[:\s]+([^\n.]{10,120})", text, re.IGNORECASE
    )
    if benefits_m:
        details["benefits"] = benefits_m.group(1).strip()

    return details


def _extract_company_hint(sender: str, subject: str, body: str) -> str:
    """
    Best-effort company name from sender email domain.
    Returns empty string if the domain looks generic.
    """
    match = re.search(r"@([\w\-]+)\.", sender)
    if match:
        domain = match.group(1).lower()
        if domain not in _GENERIC_DOMAINS:
            return domain
    return ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@gmail_bp.route("/auth")
@login_required
def gmail_auth():
    """Start Gmail OAuth — requests gmail.readonly scope."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Google OAuth not configured"}), 500

    state = secrets.token_urlsafe(32)
    session["gmail_oauth_state"] = state
    session["gmail_user_id"] = str(request.user["id"])

    params = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": _build_gmail_callback_url(),
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "access_type": "offline",
            "state": state,
            "prompt": "consent",  # always returns refresh_token
        }
    )
    return redirect(f"{_GOOGLE_AUTH_URL}?{params}")


def _popup_response(success: bool, message: str = "") -> str:
    """Return an HTML page that notifies the opener via postMessage and auto-closes."""
    msg_type = "gmail_connected" if success else "gmail_error"
    msg_detail = message if not success else ""
    fallback_url = "/?gmail_connected=1" if success else f"/?gmail_error={message}"
    status_icon = "✅" if success else "❌"
    status_text = "Gmail Connected!" if success else f"Connection failed: {message}"
    status_color = "#6ee7b7" if success else "#f87171"
    return f"""<!DOCTYPE html>
<html><head><title>Gmail OAuth</title></head>
<body style="font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;
             height:100vh;margin:0;background:#0f172a;color:#e2e8f0;flex-direction:column;gap:1rem;">
  <div style="font-size:2.5rem">{status_icon}</div>
  <p style="font-size:1.1rem;font-weight:700;color:{status_color};margin:0">{status_text}</p>
  <p style="color:#94a3b8;font-size:0.85rem;margin:0">Closing this window automatically…</p>
  <script>
    (function() {{
      var sent = false;
      function notify() {{
        if (sent) return; sent = true;
        try {{
          if (window.opener && !window.opener.closed) {{
            window.opener.postMessage({{type: '{msg_type}', detail: '{msg_detail}'}}, '*');
          }}
        }} catch(e) {{}}
      }}
      notify();
      setTimeout(function() {{
        notify();
        try {{ window.close(); }} catch(e) {{
          window.location.href = '{fallback_url}';
        }}
      }}, 1800);
    }})();
  </script>
</body></html>"""


@gmail_bp.route("/callback")
def gmail_callback():
    """Handle Gmail OAuth callback — persist tokens and close the popup window."""
    if request.args.get("error"):
        return _popup_response(False, request.args["error"])

    code = request.args.get("code")
    state = request.args.get("state")

    if not state or state != session.pop("gmail_oauth_state", None):
        return _popup_response(False, "invalid_state")

    user_id = session.pop("gmail_user_id", None)
    if not user_id:
        return _popup_response(False, "no_session")

    try:
        token_resp = http_requests.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": _build_gmail_callback_url(),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_data = token_resp.json()
    except Exception:
        return _popup_response(False, "token_exchange_failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return _popup_response(False, "no_access_token")

    db = _get_db()
    oid = _to_object_id(user_id)
    db.users.update_one(
        {"_id": oid},
        {
            "$set": {
                "gmail_access_token": access_token,
                "gmail_refresh_token": token_data.get("refresh_token", ""),
                "gmail_connected_at": datetime.now().isoformat(),
            }
        },
    )
    return _popup_response(True)


@gmail_bp.route("/status", methods=["GET"])
@login_required
def gmail_status():
    db = _get_db()
    oid = _to_object_id(request.user["id"])
    user = db.users.find_one(
        {"_id": oid},
        {"gmail_access_token": 1, "gmail_connected_at": 1, "gmail_last_sync": 1},
    )
    connected = bool(user and user.get("gmail_access_token"))
    return jsonify(
        {
            "connected": connected,
            "connected_at": (user or {}).get("gmail_connected_at", ""),
            "last_sync": (user or {}).get("gmail_last_sync", ""),
        }
    )


@gmail_bp.route("/disconnect", methods=["POST"])
@login_required
def gmail_disconnect():
    db = _get_db()
    oid = _to_object_id(request.user["id"])
    db.users.update_one(
        {"_id": oid},
        {
            "$unset": {
                "gmail_access_token": "",
                "gmail_refresh_token": "",
                "gmail_connected_at": "",
                "gmail_last_sync": "",
            }
        },
    )
    return jsonify({"message": "Gmail disconnected"})


@gmail_bp.route("/sync", methods=["POST"])
@login_required
def gmail_sync():
    """
    Scan the last 90 days of Gmail for interview/offer emails.
    Matches emails to applied jobs by company name extracted from the sender domain.
    Auto-updates job status (applied → interview or offer) and pre-fills details.
    Never downgrades status (offer stays offer even if an interview email arrives).
    """
    db = _get_db()
    oid = _to_object_id(request.user["id"])
    user = db.users.find_one(
        {"_id": oid}, {"gmail_access_token": 1, "gmail_refresh_token": 1}
    )

    if not user or not user.get("gmail_access_token"):
        return jsonify({"error": "Gmail not connected"}), 400

    access_token = user["gmail_access_token"]

    # Validate / refresh token
    probe = http_requests.get(
        f"{_GMAIL_API_BASE}/profile", headers=_headers(access_token), timeout=8
    )
    if probe.status_code == 401:
        refresh_token = user.get("gmail_refresh_token", "")
        if not refresh_token:
            return jsonify({"error": "Gmail session expired. Please reconnect."}), 401
        access_token = _refresh_access_token(refresh_token)
        if not access_token:
            return (
                jsonify({"error": "Could not refresh Gmail token. Please reconnect."}),
                401,
            )
        db.users.update_one(
            {"_id": oid}, {"$set": {"gmail_access_token": access_token}}
        )

    # Build search query — broad enough to catch invitations and offers
    search_q = (
        "subject:(interview OR offer OR congratulations OR selected OR invitation OR joining) "
        "newer_than:90d"
    )

    try:
        list_resp = http_requests.get(
            f"{_GMAIL_API_BASE}/messages",
            headers=_headers(access_token),
            params={"q": search_q, "maxResults": 50},
            timeout=15,
        )
        messages = list_resp.json().get("messages", [])
    except Exception as e:
        return jsonify({"error": f"Gmail API error: {e}"}), 500

    STATUS_RANK = {
        "new": 0,
        "saved": 0,
        "previous": 0,
        "applied": 1,
        "interview": 2,
        "offer": 3,
    }

    updates = []
    interview_count = 0
    offer_count = 0

    for msg_ref in messages[:30]:  # cap to avoid rate limits
        try:
            msg_resp = http_requests.get(
                f"{_GMAIL_API_BASE}/messages/{msg_ref['id']}",
                headers=_headers(access_token),
                params={"format": "full"},
                timeout=10,
            )
            msg = msg_resp.json()
        except Exception:
            continue

        hdrs = msg.get("payload", {}).get("headers", [])
        subject = _get_header(hdrs, "subject")
        sender = _get_header(hdrs, "from")
        date_str = _get_header(hdrs, "date")
        body = _extract_body(msg.get("payload", {}))[:2000]

        category = _classify_email(subject, body)
        if not category:
            continue

        company_hint = _extract_company_hint(sender, subject, body)
        if not company_hint:
            continue

        # Find best matching job for this user
        pattern = {"$regex": company_hint, "$options": "i"}
        job = db.jobs.find_one(
            {
                "user_id": str(request.user["id"]),
                "status": {"$in": ["applied", "new", "saved", "previous", "interview"]},
                "$or": [{"company": pattern}, {"title": pattern}],
            }
        )
        if not job:
            continue

        current_rank = STATUS_RANK.get(job.get("status", ""), 0)
        new_rank = STATUS_RANK.get(category, 0)

        # Only upgrade — never downgrade
        if new_rank <= current_rank:
            continue

        update_fields = {
            "status": category,
            "updated_at": datetime.now().isoformat(),
        }

        if category == "interview":
            extracted = _extract_interview_details(subject, body, date_str)
            existing = job.get("interview_details") or {}
            # Merge: newly extracted values override, but keep existing if we got nothing
            update_fields["interview_details"] = {
                **existing,
                **{k: v for k, v in extracted.items() if v},
            }
        elif category == "offer":
            extracted = _extract_offer_details(subject, body)
            existing = job.get("offer_details") or {}
            update_fields["offer_details"] = {
                **existing,
                **{k: v for k, v in extracted.items() if v},
            }

        db.jobs.update_one({"_id": job["_id"]}, {"$set": update_fields})

        if category == "interview":
            interview_count += 1
        else:
            offer_count += 1

        entry = {
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": category,
            "email_subject": subject[:80],
            "email_from": sender[:60],
        }
        # Surface extracted fields so the UI can show what was parsed
        if category == "interview":
            d = update_fields.get("interview_details", {})
            entry["extracted"] = {
                k: d[k]
                for k in (
                    "date",
                    "time",
                    "timezone",
                    "round",
                    "platform",
                    "meeting_link",
                    "interviewer",
                )
                if d.get(k)
            }
        else:
            d = update_fields.get("offer_details", {})
            entry["extracted"] = {
                k: d[k]
                for k in (
                    "salary",
                    "currency",
                    "joining_date",
                    "deadline",
                    "location",
                    "benefits",
                )
                if d.get(k)
            }
        updates.append(entry)

    db.users.update_one(
        {"_id": oid}, {"$set": {"gmail_last_sync": datetime.now().isoformat()}}
    )

    return jsonify(
        {
            "found": len(messages),
            "scanned": min(len(messages), 30),
            "interview": interview_count,
            "offer": offer_count,
            "updates": updates,
        }
    )
