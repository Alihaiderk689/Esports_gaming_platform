// Central API client for the Esports Pakistan Django backend.
// Set VITE_API_URL in your env; defaults to a placeholder base.

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const TOKEN_KEY = "esp_token";
const REFRESH_KEY = "esp_refresh";

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access, refresh) => {
    if (access) localStorage.setItem(TOKEN_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

async function refreshToken() {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) {
      tokenStorage.clear();
      return false;
    }
    const data = await res.json();
    tokenStorage.set(data.access || data.access_token, data.refresh || refresh);
    return true;
  } catch {
    tokenStorage.clear();
    return false;
  }
}

async function handleResponse(res) {
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    let msg = data?.detail || data?.message || data?.error;
    // DRF validation errors (e.g. password strength, duplicate email) come back
    // as { field: ["reason", ...] } with no detail/message/error wrapper.
    if (!msg && data && typeof data === "object") msg = data;
    if (msg && typeof msg === "object") msg = Object.values(msg).flat().join(" ");
    const err = /** @type {Error & {status?: number, data?: any}} */ (
      new Error(typeof msg === "string" ? msg : `Request failed (${res.status})`)
    );
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// fetch() itself throws (not a rejected-with-status response) when the
// network is genuinely unreachable — wifi drops, DNS failure, CORS
// misconfiguration. Without this, that raw browser error ("Failed to fetch",
// "Load failed", ...) surfaces straight to the UI instead of the normalized,
// friendly message every other error path already produces.
async function safeFetch(url, options) {
  try {
    return await fetch(url, options);
  } catch {
    const err = /** @type {Error & {status?: number}} */ (
      new Error("Network error — check your connection and try again.")
    );
    err.status = 0;
    throw err;
  }
}

/**
 * @param {string} path
 * @param {{method?: string, body?: any, auth?: boolean, formData?: boolean, query?: Record<string, any>}} [options]
 */
async function request(path, { method = "GET", body, auth = true, formData, query } = {}) {
  const url = new URL(API_BASE_URL + path);
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v != null && v !== "") url.searchParams.set(k, v);
    });
  }

  const headers = {};
  if (auth && tokenStorage.get()) headers.Authorization = `Bearer ${tokenStorage.get()}`;
  if (body && !formData) headers["Content-Type"] = "application/json";

  const buildBody = () => (body ? (formData ? body : JSON.stringify(body)) : undefined);

  let res = await safeFetch(url, { method, headers, body: buildBody() });

  if (res.status === 401 && auth && tokenStorage.getRefresh()) {
    const ok = await refreshToken();
    if (ok) {
      headers.Authorization = `Bearer ${tokenStorage.get()}`;
      res = await safeFetch(url, { method, headers, body: buildBody() });
    }
  }
  return handleResponse(res);
}

// For authenticated file downloads (e.g. CSV export) — a plain <a href> can't
// carry the JWT bearer token, so callers fetch the Blob here and hand it to
// the browser themselves via a synthetic download link.
/**
 * @param {string} path
 * @param {{query?: Record<string, any>}} [options]
 */
async function requestBlob(path, { query } = {}) {
  const url = new URL(API_BASE_URL + path);
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v != null && v !== "") url.searchParams.set(k, v);
    });
  }
  const headers = {};
  if (tokenStorage.get()) headers.Authorization = `Bearer ${tokenStorage.get()}`;

  let res = await safeFetch(url, { method: "GET", headers });
  if (res.status === 401 && tokenStorage.getRefresh()) {
    const ok = await refreshToken();
    if (ok) {
      headers.Authorization = `Bearer ${tokenStorage.get()}`;
      res = await safeFetch(url, { method: "GET", headers });
    }
  }
  if (!res.ok) {
    const err = /** @type {Error & {status?: number}} */ (new Error(`Request failed (${res.status})`));
    err.status = res.status;
    throw err;
  }
  return res.blob();
}

export const api = {
  get: (p, opts) => request(p, { ...opts, method: "GET" }),
  post: (p, body, opts) => request(p, { ...opts, method: "POST", body }),
  patch: (p, body, opts) => request(p, { ...opts, method: "PATCH", body }),
  put: (p, body, opts) => request(p, { ...opts, method: "PUT", body }),
  delete: (p, opts) => request(p, { ...opts, method: "DELETE" }),
  getBlob: (p, opts) => requestBlob(p, opts),
};

export const API_BASE = API_BASE_URL;