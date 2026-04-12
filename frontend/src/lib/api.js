const BASE = process.env.NEXT_PUBLIC_API_BASE || '';

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
