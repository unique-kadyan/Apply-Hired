// Runtime base detection — never baked-in at build time.
// Dev (localhost/127.0.0.1): Flask runs on :5000, Next.js dev server on :3000.
// Production (any other host): Flask serves both API and static files on the same origin.
const BASE =
  process.env.NEXT_PUBLIC_API_BASE !== undefined ||
  process.env.NEXT_PUBLIC_API_BASE !== null
    ? process.env.NEXT_PUBLIC_API_BASE
    : "https://kaddy-backend.onrender.com";

function handleResponse(r) {
  if (r.status === 401) {
    window.dispatchEvent(new CustomEvent("session:expired"));
    return Promise.reject(new Error("session_expired"));
  }
  return r.json();
}

const api = {
  get: (url) => fetch(`${BASE}${url}`).then(handleResponse),
  post: (url, data) =>
    fetch(`${BASE}${url}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handleResponse),
  put: (url, data) =>
    fetch(`${BASE}${url}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handleResponse),
  upload: (url, formData) =>
    fetch(`${BASE}${url}`, {
      method: "POST",
      body: formData,
    }).then(handleResponse),
  delete: (url) =>
    fetch(`${BASE}${url}`, {
      method: "DELETE",
    }).then(handleResponse),
};

export default api;
