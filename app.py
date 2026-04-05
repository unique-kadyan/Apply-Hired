"""Flask application factory — registers blueprints and serves the SPA."""

import os

from flask import Flask, request, jsonify, send_from_directory

from tracker import init_db
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.jobs import jobs_bp
from routes.search import search_bp
from routes.payment import payment_bp


def create_app() -> Flask:
    app = Flask(__name__, static_folder="frontend/build", static_url_path="")
    app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = int(os.environ.get("SESSION_LIFETIME_DAYS", 30)) * 86400
    app.config["SESSION_COOKIE_SECURE"] = not os.environ.get("FLASK_DEBUG")

    # Register blueprints
    app.register_blueprint(auth_bp)       # /api/auth/*
    app.register_blueprint(profile_bp)    # /api/profile/*
    app.register_blueprint(jobs_bp)       # /api/jobs/*, /api/apply, /api/auto-apply
    app.register_blueprint(search_bp)     # /api/search/*, /api/stats
    app.register_blueprint(payment_bp)    # /api/payment/*

    # Serve React SPA
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(404)
    def spa_fallback(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = not os.environ.get("RENDER")
    print("\n  Job Application Bot - API Server")
    print(f"  Running on port {port}")
    print("  API:      /api/")
    print("  Frontend: / (production build)\n")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
