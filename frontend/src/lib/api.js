// Runtime base detection — evaluated in the browser, never baked-in at build time.
// Dev  (localhost / 127.0.0.1): Next.js on :3000, Flask on :5000 → cross-origin call needed.
// Prod (any other hostname)   : Flask serves static files AND API on the same origin → empty base.
function getBase() {
  if (typeof window === 'undefined') return ''; // SSR / static-export build phase
  const h = window.location.hostname;
  if (h === 'localhost' || h === '127.0.0.1') {
    return 'http://localhost:5000';
  }
  return ''; // same-origin in production
}

const BASE = getBase();

function handleResponse(r) {
  if (r.status === 401) {
    window.dispatchEvent(new CustomEvent('session:expired'));
    return Promise.reject(new Error('session_expired'));
  }
  return r.json();
}

const api = {
  get: (url) => fetch(`${BASE}${url}`).then(handleResponse),
  post: (url, data) => fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(handleResponse),
  put: (url, data) => fetch(`${BASE}${url}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(handleResponse),
  upload: (url, formData) => fetch(`${BASE}${url}`, {
    method: 'POST',
    body: formData,
  }).then(handleResponse),
  delete: (url) => fetch(`${BASE}${url}`, {
    method: 'DELETE',
  }).then(handleResponse),
};

export default api;
