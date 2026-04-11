const BASE = process.env.NEXT_PUBLIC_API_BASE || '';

const api = {
  get: (url) => fetch(`${BASE}${url}`).then(r => r.json()),
  post: (url, data) => fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json()),
  put: (url, data) => fetch(`${BASE}${url}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json()),
  upload: (url, formData) => fetch(`${BASE}${url}`, {
    method: 'POST',
    body: formData,
  }).then(r => r.json()),
};

export default api;
