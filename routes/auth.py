"""Auth routes — signup, login, logout, Google OAuth."""

import os
import random
import secrets
from datetime import datetime
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, request, jsonify, session, redirect

from middleware import DEFAULT_PROFILE
from services.email_service import is_smtp_configured, send_otp_email
from tracker import (
    create_user, authenticate_user, get_user_by_id,
    update_user_profile, _get_db,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Google OAuth config
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# In-memory pending OTP store
_pending_otps: dict = {}


def _build_callback_url() -> str:
    url = request.url_root.rstrip("/") + "/api/auth/google/callback"
    if url.startswith("http://") and "localhost" not in url and "127.0.0.1" not in url:
        url = url.replace("http://", "https://", 1)
    return url


def _init_profile(user_id: int, name: str, email: str, extra: dict | None = None):
    """Set the default profile for a newly created user."""
    profile = dict(DEFAULT_PROFILE)
    profile["name"] = name
    profile["email"] = email
    if extra:
        profile.update(extra)
    update_user_profile(user_id, profile)


# ---- Email / password auth ------------------------------------------------

@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = _get_db()
    existing = db.users.find_one({"email": email})
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    # No SMTP → create account directly
    if not is_smtp_configured():
        user = create_user(name, email, password)
        if not user:
            return jsonify({"error": "An account with this email already exists"}), 409
        _init_profile(user["id"], name, email)
        session.permanent = True
        session["user_id"] = user["id"]
        return jsonify({
            "message": "Account created successfully",
            "user": {"id": user["id"], "name": name, "email": email},
        }), 201

    # Send OTP
    otp = str(random.randint(100000, 999999))
    if not send_otp_email(email, otp):
        return jsonify({"error": "Failed to send verification email. Please try again or use Google Sign-In.", "use_google": True}), 500

    _pending_otps[email] = {
        "otp": otp, "name": name, "password": password,
        "expires": datetime.now().timestamp() + 600,
    }
    return jsonify({"message": "Verification code sent to your email", "needs_otp": True})


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not email or not otp:
        return jsonify({"error": "Email and verification code are required"}), 400

    pending = _pending_otps.get(email)
    if not pending:
        return jsonify({"error": "No pending verification. Please sign up again."}), 400
    if datetime.now().timestamp() > pending["expires"]:
        del _pending_otps[email]
        return jsonify({"error": "Verification code expired. Please sign up again."}), 400
    if otp != pending["otp"]:
        return jsonify({"error": "Invalid verification code"}), 400

    name, password = pending["name"], pending["password"]
    del _pending_otps[email]

    user = create_user(name, email, password)
    if not user:
        return jsonify({"error": "An account with this email already exists"}), 409

    _init_profile(user["id"], name, email)
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({
        "message": "Account verified and created successfully",
        "user": {"id": user["id"], "name": name, "email": email},
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = authenticate_user(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({
        "message": "Logged in successfully",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


# In-memory reset tokens: { token: { "email": ..., "expires": timestamp } }
_reset_tokens: dict = {}


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Check if user exists
    db = _get_db()
    user = db.users.find_one({"email": email})
    # Always return success to prevent email enumeration
    if not user:
        return jsonify({"message": "If that email exists, a reset link has been sent."})

    # Generate reset token
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {
        "email": email,
        "expires": datetime.now().timestamp() + 600,  # 10 minutes
    }

    # Build reset URL
    base_url = request.url_root.rstrip("/")
    if base_url.startswith("http://") and "localhost" not in base_url and "127.0.0.1" not in base_url:
        base_url = base_url.replace("http://", "https://", 1)
    reset_url = f"{base_url}/?reset_token={token}"

    # Send email
    _send_reset_email(email, reset_url)

    return jsonify({"message": "If that email exists, a reset link has been sent."})


def _send_reset_email(to_email: str, reset_url: str):
    """Send password reset email via available email provider."""
    html = f"""
    <div style="font-family:'Segoe UI',system-ui,sans-serif;max-width:480px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px">
        <h1 style="color:#60a5fa;margin:0 0 0.5rem">JobBot</h1>
        <p style="color:#94a3b8;margin:0 0 1.5rem">Reset your password</p>
        <p style="color:#cbd5e1;line-height:1.6;margin:0 0 1.5rem">
            Click the button below to reset your password. This link expires in 10 minutes.
        </p>
        <a href="{reset_url}" style="display:inline-block;background:#2563eb;color:#fff;
           padding:0.75rem 2rem;border-radius:8px;text-decoration:none;font-weight:600">
            Reset Password
        </a>
        <p style="color:#64748b;font-size:0.82rem;margin:1.5rem 0 0">
            If you didn't request this, ignore this email.
        </p>
    </div>
    """
    import os
    # Try Brevo
    brevo_key = os.environ.get("BREVO_API_KEY", "")
    if brevo_key:
        try:
            import requests as req
            smtp_email = os.environ.get("SMTP_EMAIL", os.environ.get("BREVO_FROM", "noreply@jobbot.app"))
            resp = req.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                json={
                    "sender": {"name": "JobBot", "email": smtp_email},
                    "to": [{"email": to_email}],
                    "subject": "JobBot — Reset your password",
                    "htmlContent": html,
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return
        except Exception:
            pass

    # Try SMTP
    smtp_email = os.environ.get("SMTP_EMAIL", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    if smtp_email and smtp_pass:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart("alternative")
            msg["From"] = f"JobBot <{smtp_email}>"
            msg["To"] = to_email
            msg["Subject"] = "JobBot — Reset your password"
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                              int(os.environ.get("SMTP_PORT", 587)), timeout=10) as server:
                server.starttls()
                server.login(smtp_email, smtp_pass)
                server.sendmail(smtp_email, to_email, msg.as_string())
        except Exception:
            pass


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()
    new_password = data.get("password", "")

    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    pending = _reset_tokens.get(token)
    if not pending:
        return jsonify({"error": "Invalid or expired reset link"}), 400
    if datetime.now().timestamp() > pending["expires"]:
        del _reset_tokens[token]
        return jsonify({"error": "Reset link has expired. Please request a new one."}), 400

    email = pending["email"]
    del _reset_tokens[token]

    # Update password
    from werkzeug.security import generate_password_hash
    db = _get_db()
    result = db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": generate_password_hash(new_password)}},
    )
    if result.modified_count == 0:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"message": "Password reset successfully. You can now sign in."})


@auth_bp.route("/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"user": None})
    return jsonify({
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
    })


# ---- Google OAuth ----------------------------------------------------------

@auth_bp.route("/google")
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Google OAuth not configured."}), 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _build_callback_url(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    })
    return redirect(f"{_GOOGLE_AUTH_URL}?{params}")


@auth_bp.route("/google/callback")
def google_callback():
    error = request.args.get("error")
    if error:
        return redirect("/?auth_error=" + error)

    code = request.args.get("code")
    state = request.args.get("state")

    if not state or state != session.pop("oauth_state", None):
        return redirect("/?auth_error=invalid_state")

    callback_url = _build_callback_url()

    # Exchange code for tokens
    try:
        token_resp = http_requests.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        }, timeout=10)
        token_data = token_resp.json()
    except Exception:
        return redirect("/?auth_error=token_exchange_failed")

    access_token = token_data.get("access_token")
    if not access_token:
        return redirect("/?auth_error=no_access_token")

    # Fetch Google user info
    try:
        user_resp = http_requests.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        google_user = user_resp.json()
    except Exception:
        return redirect("/?auth_error=userinfo_failed")

    email = google_user.get("email", "")
    name = google_user.get("name", email.split("@")[0])
    if not email:
        return redirect("/?auth_error=no_email")

    # Find or create user
    db = _get_db()
    row = db.users.find_one({"email": email.lower()})

    if row:
        user_id = str(row["_id"])
    else:
        user = create_user(name, email, secrets.token_urlsafe(32))
        if not user:
            return redirect("/?auth_error=account_creation_failed")
        user_id = user["id"]
        _init_profile(user_id, name, email, {"picture": google_user.get("picture", "")})

    session.permanent = True
    session["user_id"] = user_id
    return redirect("/?auth_success=1")
