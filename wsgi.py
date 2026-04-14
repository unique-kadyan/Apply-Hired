# ruff: noqa: I001, E402
"""WSGI entrypoint with gevent monkey-patching applied before any other import.

Long-lived SSE connections require a cooperative async worker; gevent makes the
stdlib (socket, threading, time.sleep, ssl) non-blocking. Monkey-patching MUST
run before pymongo, requests, flask, etc. are imported — otherwise their
sockets stay blocking and SSE clients pin the worker.

Import order is intentional and cannot be alphabetized; ruff isort/E402 are
disabled at file scope rather than per-line.
"""

from gevent import monkey

monkey.patch_all()

from app import app

if __name__ == "__main__":
    import os
    from tracker import init_db

    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)  # nosec B104
