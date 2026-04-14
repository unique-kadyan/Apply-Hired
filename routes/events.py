"""Server-Sent Events stream — pushes per-user updates to the SPA.

Event types currently published:
  search_progress  — search status updates (running, message, progress)
  jobs_changed     — job list mutated (new jobs, status change, etc.)
  gmail_synced     — Gmail sync finished (counts of interview/offer found)
  job_updated      — single job status updated (id + new status)

The endpoint streams `text/event-stream`. A heartbeat comment is emitted every
15 s so Render's load balancer / Cloudflare don't kill the idle connection.
"""

import json
import logging

from flask import Blueprint, Response, request, stream_with_context

from middleware import login_required
from services.events import drain, subscribe, unsubscribe

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__, url_prefix="/api/events")


@events_bp.route("/stream")
@login_required
def stream():
    user_id = str(request.user["id"])
    q = subscribe(user_id)

    @stream_with_context
    def gen():
        try:
            yield "retry: 3000\n\n"
            yield ": connected\n\n"
            while True:
                msg = drain(q, timeout=15.0)
                if msg is None:
                    yield ": heartbeat\n\n"
                    continue
                payload = json.dumps(msg["data"], default=str)
                yield f"event: {msg['type']}\ndata: {payload}\n\n"
        except GeneratorExit:
            pass
        except Exception as e:
            logger.warning(f"SSE stream error user={user_id}: {e}")
        finally:
            unsubscribe(user_id, q)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
