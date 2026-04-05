"""Email service — sends OTP verification emails via Resend (HTTP) or SMTP fallback."""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# Resend (HTTP-based, works on Render)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "JobBot <onboarding@resend.dev>")

# SMTP fallback (works locally, blocked on Render free tier)
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))


def is_smtp_configured() -> bool:
    return bool(RESEND_API_KEY or (SMTP_EMAIL and SMTP_PASSWORD))


def _build_html(otp: str) -> str:
    return f"""
    <div style="font-family:'Segoe UI',system-ui,sans-serif;max-width:480px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px">
        <h1 style="color:#60a5fa;margin:0 0 0.5rem">JobBot</h1>
        <p style="color:#94a3b8;margin:0 0 1.5rem">Verify your email to create your account</p>
        <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;
                    padding:1.5rem;text-align:center;margin-bottom:1.5rem">
            <p style="color:#94a3b8;margin:0 0 0.5rem;font-size:0.9rem">Your verification code</p>
            <div style="font-size:2.5rem;font-weight:800;letter-spacing:0.3em;color:#fff">{otp}</div>
        </div>
        <p style="color:#64748b;font-size:0.82rem;margin:0">
            This code expires in 10 minutes. If you didn't request this, ignore this email.
        </p>
    </div>
    """


def _send_via_resend(to_email: str, otp: str) -> bool:
    """Send email via Resend HTTP API (works on Render)."""
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": f"JobBot — Your verification code is {otp}",
            "html": _build_html(otp),
        })
        print(f"[Resend] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Resend] FAILED: {e}")
        return False


def _send_via_smtp(to_email: str, otp: str) -> bool:
    """Send email via SMTP (works locally)."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"JobBot <{SMTP_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = f"JobBot — Your verification code is {otp}"
    msg.attach(MIMEText(_build_html(otp), "html"))

    try:
        print(f"[SMTP] Connecting to {SMTP_HOST}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        print(f"[SMTP] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[SMTP] FAILED: {e}")
        return False


def _send_via_brevo(to_email: str, otp: str) -> bool:
    """Send email via Brevo (Sendinblue) HTTP API — free 300/day, no domain needed."""
    brevo_key = os.environ.get("BREVO_API_KEY", "")
    if not brevo_key:
        return False
    try:
        import requests
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": brevo_key, "Content-Type": "application/json"},
            json={
                "sender": {"name": "JobBot", "email": os.environ.get("BREVO_FROM", SMTP_EMAIL or "noreply@jobbot.app")},
                "to": [{"email": to_email}],
                "subject": f"JobBot — Your verification code is {otp}",
                "htmlContent": _build_html(otp),
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            print(f"[Brevo] OTP sent to {to_email}")
            return True
        print(f"[Brevo] FAILED: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"[Brevo] FAILED: {e}")
        return False


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP email. Tries Brevo → Resend → SMTP in order."""
    if os.environ.get("BREVO_API_KEY"):
        if _send_via_brevo(to_email, otp):
            return True

    if RESEND_API_KEY:
        if _send_via_resend(to_email, otp):
            return True

    if SMTP_EMAIL and SMTP_PASSWORD:
        if _send_via_smtp(to_email, otp):
            return True

    logger.error("No email provider configured or all failed")
    return False
