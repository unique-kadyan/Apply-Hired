"""Auth routes — signup, login, logout, Google OAuth."""

import os
import random
import secrets
from datetime import datetime
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, request, jsonify, session, redirect

from middleware import DEFAULT_PROFILE, get_user_profile
from services.email_service import is_smtp_configured, send_otp_email
from tracker import (
    create_user, authenticate_user, get_user_by_id,
    update_user_profile, _get_conn,
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

    conn = _get_conn()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    # No SMTP → create account directly
    if not is_smtp_configured():
        user = create_user(name, email, password)
        if not user:
            return jsonify({"error": "An account with this email already exists"}), 409
        _init_profile(user["id"], name, email)
        session["user_id"] = user["id"]
        return jsonify({
            "message": "Account created successfully",
            "user": {"id": user["id"], "name": name, "email": email},
        }), 201

    # Send OTP
    otp = str(random.randint(100000, 999999))
    if not send_otp_email(email, otp):
        return jsonify({"error": "Failed to send verification email. Please try again."}), 500

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

    session["user_id"] = user["id"]
    return jsonify({
        "message": "Logged in successfully",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


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
    conn = _get_conn()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()

    if row:
        user_id = row["id"]
    else:
        user = create_user(name, email, secrets.token_urlsafe(32))
        if not user:
            conn.close()
            return redirect("/?auth_error=account_creation_failed")
        user_id = user["id"]
        _init_profile(user_id, name, email, {"picture": google_user.get("picture", "")})

    conn.close()
    session["user_id"] = user_id
    return redirect("/?auth_success=1")
