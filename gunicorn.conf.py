"""Gunicorn production config — single source of truth for worker tuning.

Procfile invokes: gunicorn wsgi:app --config gunicorn.conf.py
Override per-deploy via env vars (WEB_CONCURRENCY, GUNICORN_TIMEOUT, etc.) without
editing this file or the Procfile.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# gevent: cooperative async worker — required for SSE (long-lived HTTP streams).
# 1 worker × 1000 connections handles ~1000 concurrent SSE clients on a 0.5-CPU
# Render free instance. Bump WEB_CONCURRENCY only if CPU-bound work dominates;
# SSE is I/O-bound and benefits from connections, not workers.
worker_class = "gevent"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_connections = int(os.environ.get("WORKER_CONNECTIONS", "1000"))

# Long timeout for slow scrapers / AI calls; keep-alive matches Render's LB
# idle window so SSE heartbeats keep the connection warm.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "75"))
graceful_timeout = 30

# Logs to stdout/stderr — Render captures these automatically.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Preload conserves memory across workers but conflicts with gevent monkey-patching
# (the patch must run inside each worker, not in the master). Leave disabled.
preload_app = False
