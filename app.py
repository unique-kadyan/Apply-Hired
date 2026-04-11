"""Flask application factory — registers blueprints and serves the SPA."""

import os

from flask import Flask, jsonify, request, send_from_directory

from routes.auth import auth_bp
from routes.gmail import gmail_bp
from routes.jobs import jobs_bp
from routes.payment import payment_bp
from routes.profile import profile_bp
from routes.search import search_bp
from services.scheduler import start_scheduler, stop_scheduler
from tracker import init_db


def create_app() -> Flask:
    app = Flask(__name__, static_folder="frontend/build", static_url_path="")
    app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = int(float(os.environ.get("SESSION_LIFETIME_HOURS", 720)) * 3600)
    app.config["SESSION_COOKIE_SECURE"] = not os.environ.get("FLASK_DEBUG")

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(gmail_bp)

    start_scheduler()

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        print(f"  Public URL: {render_url}")
        print(f"  Health:     {render_url}/health")

    app.teardown_appcontext(lambda _: stop_scheduler())

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(404)
    def spa_fallback(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        if request.path.startswith("/_next/"):
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
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)  # nosec B104
