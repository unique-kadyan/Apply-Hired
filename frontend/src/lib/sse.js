// Singleton SSE bus — one EventSource for the whole app, dispatched to many React subscribers.
// Auto-reconnects on disconnect (browsers do this natively for EventSource).
// Force-reconnects when the tab regains focus after >30 s away (browsers throttle background tabs;
// the connection may be stale by the time the user returns).

function getBase() {
  if (typeof window === 'undefined') return '';
  const h = window.location.hostname;
  if (h === 'localhost' || h === '127.0.0.1') return 'http://localhost:5000';
  return '';
}

let _es = null;
let _lastFocus = Date.now();
const _listeners = new Map(); // event_type -> Set<callback>
const _registeredOnES = new Set();

function attachListener(eventType) {
  if (!_es || _registeredOnES.has(eventType)) return;
  _es.addEventListener(eventType, (e) => {
    let data = {};
    try { data = JSON.parse(e.data); } catch { /* heartbeat-shaped events: ignore */ }
    const subs = _listeners.get(eventType);
    if (!subs) return;
    subs.forEach((cb) => {
      try { cb(data); } catch (err) { console.error(`SSE handler error (${eventType}):`, err); }
    });
  });
  _registeredOnES.add(eventType);
}

function ensureConnected() {
  if (typeof window === 'undefined') return;
  if (_es && (_es.readyState === EventSource.OPEN || _es.readyState === EventSource.CONNECTING)) return;
  try { if (_es) _es.close(); } catch { /* ignore */ }
  _es = new EventSource(`${getBase()}/api/events/stream`, { withCredentials: true });
  _registeredOnES.clear();
  // Re-attach all known listeners on the fresh EventSource.
  for (const eventType of _listeners.keys()) attachListener(eventType);
  _es.onerror = () => {
    // Browser will auto-retry per server `retry:` directive (3000ms). Nothing to do here.
  };
}

if (typeof window !== 'undefined') {
  window.addEventListener('focus', () => {
    const away = Date.now() - _lastFocus;
    _lastFocus = Date.now();
    // If the tab was background for >30 s, force a fresh connection so we don't sit on a stale one.
    if (away > 30_000) {
      try { if (_es) _es.close(); } catch { /* ignore */ }
      _es = null;
      if (_listeners.size > 0) ensureConnected();
    }
  });
  window.addEventListener('blur', () => { _lastFocus = Date.now(); });
}

export function subscribe(eventType, callback) {
  if (typeof window === 'undefined') return () => {};
  if (!_listeners.has(eventType)) _listeners.set(eventType, new Set());
  _listeners.get(eventType).add(callback);
  ensureConnected();
  attachListener(eventType);
  return () => {
    const subs = _listeners.get(eventType);
    if (!subs) return;
    subs.delete(callback);
    if (subs.size === 0) _listeners.delete(eventType);
    if (_listeners.size === 0 && _es) {
      try { _es.close(); } catch { /* ignore */ }
      _es = null;
      _registeredOnES.clear();
    }
  };
}

export default { subscribe };
