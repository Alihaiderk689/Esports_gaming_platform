// Handles the redirect leg of Google sign-in: building the auth URL with a
// nonce (replay protection, required by Google for response_type=id_token),
// and parsing the id_token back out of the URL fragment on return. The
// fragment never reaches our server — Google puts it there specifically so
// the token doesn't end up in server access logs — so it must be read
// client-side via window.location.hash, not as a query param.
const NONCE_KEY = "esp_google_nonce";
const FROM_KEY = "esp_google_from";

export function startGoogleSignIn(from) {
  const nonce = crypto.randomUUID();
  sessionStorage.setItem(NONCE_KEY, nonce);
  sessionStorage.setItem(FROM_KEY, from || "/");
  const params = new URLSearchParams({
    client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
    redirect_uri: `${window.location.origin}/auth/google/callback`,
    response_type: "id_token",
    scope: "openid email profile",
    nonce,
    prompt: "select_account",
  });
  window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

// JWTs are three base64url segments joined by '.' — decoding the middle
// segment (the payload) is enough to read the nonce claim client-side as a
// defense-in-depth check. The token itself is still fully verified
// server-side (signature, audience, expiry) in GoogleLoginView regardless.
function decodeJwtPayload(token) {
  const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(decodeURIComponent(escape(atob(base64))));
}

// Returns { idToken, from } on success, or throws an Error with a
// user-facing message.
export function consumeGoogleCallback() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const expectedNonce = sessionStorage.getItem(NONCE_KEY);
  const from = sessionStorage.getItem(FROM_KEY) || "/";
  sessionStorage.removeItem(NONCE_KEY);
  sessionStorage.removeItem(FROM_KEY);

  if (params.get("error")) {
    throw new Error("Google sign-in was cancelled or denied.");
  }
  const idToken = params.get("id_token");
  if (!idToken) {
    throw new Error("Google sign-in failed — no credential was returned. Please try again.");
  }

  let nonce;
  try {
    nonce = decodeJwtPayload(idToken).nonce;
  } catch {
    throw new Error("Google sign-in returned an unreadable credential. Please try again.");
  }
  if (!expectedNonce || nonce !== expectedNonce) {
    throw new Error("Google sign-in failed a security check. Please try again.");
  }

  return { idToken, from };
}
