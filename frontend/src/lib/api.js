// Central API client for the Esports Pakistan Django backend.
// Set VITE_API_URL in your env; defaults to a placeholder base.

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// The access token lives in memory only (never localStorage/sessionStorage)
// so an XSS payload can't read it off disk — it's gone on a full page
// reload, recovered via a silent refresh() call below against the httpOnly
// refresh-token cookie the backend sets on login (core/cookies.py). The
// refresh token itself is never readable from JS at all.
let accessToken = null;

export const tokenStorage = {
  get: () => accessToken,
  set: (access) => {
    if (access) accessToken = access;
  },
  clear: () => {
    accessToken = null;
  },
};

// Exported so appauth.jsx can call it directly on mount to silently
// re-establish an access token from the httpOnly cookie (the in-memory
// token above doesn't survive a page reload).
export async function refreshToken() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/token/refresh/`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      tokenStorage.clear();
      return false;
    }
    const data = await res.json();
    tokenStorage.set(data.access || data.access_token);
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
 * @param {{method?: string, body?: any, auth?: boolean, formData?: boolean, query?: Record<string, any>, withCredentials?: boolean}} [options]
 */
async function request(path, { method = "GET", body, auth = true, formData, query, withCredentials = false } = {}) {
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
  const fetchOpts = { method, headers, body: buildBody() };
  // Only the auth endpoints that touch the httpOnly refresh cookie
  // (login/register/google-login/logout) need this — everything else stays
  // credentials-free, matching the existing least-privilege CORS posture.
  if (withCredentials) fetchOpts.credentials = "include";

  let res = await safeFetch(url, fetchOpts);

  if (res.status === 401 && auth) {
    // There's no client-readable refresh token to check anymore (it's in an
    // httpOnly cookie) — just attempt the refresh and let the response say
    // whether it worked.
    const ok = await refreshToken();
    if (ok) {
      headers.Authorization = `Bearer ${tokenStorage.get()}`;
      res = await safeFetch(url, fetchOpts);
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
  if (res.status === 401) {
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