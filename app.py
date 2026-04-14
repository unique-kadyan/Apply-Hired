"""Flask application factory — registers blueprints and serves the SPA.

Production entrypoint is wsgi.py (which monkey-patches gevent before importing
this module). Local dev: `python wsgi.py` or `gunicorn --reload wsgi:app --config gunicorn.conf.py`.
"""

import atexit
import logging
import os

from flask import Flask, jsonify, request, send_from_directory

from routes.auth import auth_bp
from routes.config_routes import config_bp
from routes.events import events_bp
from routes.gmail import gmail_bp
from routes.jobs import jobs_bp
from routes.payment import payment_bp
from routes.profile import profile_bp
from routes.search import search_bp
from services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="frontend/build", static_url_path="")
    app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = int(float(os.environ.get("SESSION_LIFETIME_HOURS", 720)) * 3600)
    app.config["SESSION_COOKIE_SECURE"] = not os.environ.get("FLASK_DEBUG")

    app.register_blueprint(auth_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(events_bp)

    start_scheduler()
    atexit.register(stop_scheduler)

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        logger.info(f"Public URL: {render_url}")
        logger.info(f"Health: {render_url}/health")

    @app.route("/health")
    def health():
        """Liveness + readiness probe — pings MongoDB so Render restarts on DB failure."""
        try:
            from tracker import _get_db
            _get_db().command("ping")
            return jsonify({"status": "ok", "db": "ok"}), 200
        except Exception as e:
            logger.warning(f"Health check degraded: {e}")
            return jsonify({"status": "degraded", "db": "unreachable"}), 503

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
