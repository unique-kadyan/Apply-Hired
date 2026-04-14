"""In-process per-user pub/sub for SSE streams.

Each connected SSE client gets its own bounded queue. Publishers fan out events
to every queue subscribed to that user_id. If a queue is full (slow client) we
drop the event for that client only — never block the publisher.

Single-process only. If you ever scale to multiple gunicorn processes, swap
the in-memory subscriber map for Redis pub/sub.
"""

import logging
import threading
from datetime import datetime, timezone
from queue import Empty, Full, Queue

logger = logging.getLogger(__name__)

_QUEUE_MAX = 100
_lock = threading.Lock()
_subscribers: dict[str, list[Queue]] = {}


def subscribe(user_id: str) -> Queue:
    q: Queue = Queue(maxsize=_QUEUE_MAX)
    with _lock:
        _subscribers.setdefault(user_id, []).append(q)
    logger.debug(f"SSE subscribe user={user_id} subs={len(_subscribers[user_id])}")
    return q


def unsubscribe(user_id: str, q: Queue) -> None:
    with _lock:
        if user_id in _subscribers:
            _subscribers[user_id] = [s for s in _subscribers[user_id] if s is not q]
            if not _subscribers[user_id]:
                del _subscribers[user_id]


def publish(user_id: str, event_type: str, data: dict) -> None:
    """Fan out an event to all of this user's subscribers. Never raises."""
    msg = {
        "type": event_type,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        targets = list(_subscribers.get(str(user_id), []))
    for q in targets:
        try:
            q.put_nowait(msg)
        except Full:
            logger.warning(f"SSE queue full for user={user_id} — dropping {event_type}")


def drain(q: Queue, timeout: float = 15.0):
    """Yield the next event, or None on timeout (caller emits a heartbeat)."""
    try:
        return q.get(timeout=timeout)
    except Empty:
        return None
