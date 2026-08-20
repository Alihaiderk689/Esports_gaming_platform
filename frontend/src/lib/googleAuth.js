// Handles the redirect leg of Google sign-in: fetching a server-minted
// nonce/state pair, building the auth URL with them, and parsing the
// id_token + state back out of the URL fragment on return. The fragment
// never reaches our server — Google puts it there specifically so the token
// doesn't end up in server access logs — so it must be read client-side via
// window.location.hash, not as a query param.
//
// The nonce/state come from the backend (core.views.GoogleOAuthStartView)
// rather than being generated here: `state` is a signed token the backend
// can independently re-derive the expected nonce from later, so the server
// verifies the round trip itself instead of trusting whatever nonce value
// the client claims it used. See docs/SECURITY.md#google-oauth.
import { API_BASE } from "./api";

const STATE_KEY = "esp_google_state";
const FROM_KEY = "esp_google_from";

export async function startGoogleSignIn(from) {
  const res = await fetch(`${API_BASE}/api/auth/google/start/`);
  if (!res.ok) {
    throw new Error("Could not start Google sign-in. Please try again.");
  }
  const { nonce, state } = await res.json();

  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(FROM_KEY, from || "/");
  const params = new URLSearchParams({
    client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
    redirect_uri: `${window.location.origin}/auth/google/callback`,
    response_type: "id_token",
    scope: "openid email profile",
    nonce,
    state,
    prompt: "select_account",
  });
  window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

// Returns { idToken, state, from } on success, or throws an Error with a
// user-facing message. The real nonce check happens server-side
// (GoogleLoginView) against the state below — this only confirms Google
// echoed back the same state this browser tab started with, so a stray or
// stale callback doesn't get forwarded to the backend at all.
export function consumeGoogleCallback() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const from = sessionStorage.getItem(FROM_KEY) || "/";
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(FROM_KEY);

  if (params.get("error")) {
    throw new Error("Google sign-in was cancelled or denied.");
  }
  const idToken = params.get("id_token");
  const state = params.get("state");
  if (!idToken || !state) {
    throw new Error("Google sign-in failed — no credential was returned. Please try again.");
  }
  if (!expectedState || state !== expectedState) {
    throw new Error("Google sign-in failed a security check. Please try again.");
  }

  return { idToken, state, from };
}
