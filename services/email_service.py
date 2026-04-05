"""Email service — sends OTP verification emails via SMTP."""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))


def is_smtp_configured() -> bool:
    return bool(SMTP_EMAIL and SMTP_PASSWORD)


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send a styled OTP verification email. Returns True on success."""
    if not is_smtp_configured():
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"JobBot <{SMTP_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = f"JobBot — Your verification code is {otp}"

    html = f"""
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
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False
