---
feature: auth
status: stable
last_updated: 2026-08-30
backend_paths:
  - backend/core/
frontend_paths:
  - frontend/src/pages/auth.jsx
  - frontend/src/pages/googlecallback.jsx
  - frontend/src/pages/verifyemail.jsx
  - frontend/src/pages/forgotpassword.jsx
  - frontend/src/pages/resetpassword.jsx
  - frontend/src/pages/accountsettings.jsx
  - frontend/src/pages/adminusers.jsx
  - frontend/src/lib/appauth.jsx
  - frontend/src/lib/googleAuth.js
related_docs:
  - docs/SECURITY.md#authentication
  - docs/ARCHITECTURE.md#authentication-architecture
  - docs/EDGE_CASES.md (Registration & email-OTP verification, Google OAuth, Account deletion & data integrity sections)
---

# Auth (registration, login, Google OAuth, sessions, admin user management)

## What it does

Everything under `core.User` (custom model, email as `USERNAME_FIELD`, no `username` field): password registration with email-OTP verification, password login, Google OAuth login, JWT issuance/refresh/revocation, password reset, and admin management of user accounts (including staff grant/revoke). Player listing/profile/follow endpoints also live in `core` but are lighter-weight CRUD, not part of the auth flow itself.

## How it works

**Registration never creates a `User` directly.** `RegisterSerializer.create()` (`core/serializers.py`) writes a `PendingRegistration` row (hashed password via `make_password`, never plaintext) and emails a 6-digit OTP (`core/otp.py`). Only `POST /api/auth/verify-email/` (`VerifyEmailView`) with the correct code creates the real `User` (and `Organizer`, if the signup included an organizer application) inside one transaction, then deletes the pending row. Two people registering the same email before either verifies: `update_or_create` silently lets the second overwrite the first's pending row — deliberate, not a bug (see EDGE_CASES).

**OTP defenses** (`core/otp.py`): only the hash is stored (`otp_hash`), 5-attempt lockout (`otp_attempts`), 10-minute expiry (`otp_expires_at`), 60-second resend cooldown (`can_resend()`). Unknown-email and wrong/expired/locked all return the identical `{'otp': 'Invalid or expired code.'}` shape to prevent account enumeration.

**Login** (`LoginView`) — email + password → JWT pair. **Google OAuth** (`GoogleLoginView`) — implicit-flow redirect (not GIS `renderButton()`); frontend gets `id_token` in the URL fragment (never sent to any server), backend verifies it against Google's public certs (`google.oauth2.id_token.verify_oauth2_token`), checks `email_verified`, `get_or_create`s the `User` by email (can backfill `google_id` onto an existing password account with a matching Google-verified email). Nonce is server-verifiable: `GoogleOAuthStartView` issues a signed `state` (`TimestampSigner`, 5-min max age) embedding the nonce; `GoogleLoginView` re-derives the expected nonce from `state` itself rather than trusting the client. `state` is single-use after a successful login (`cache.set(f'google_oauth_state_used:{state}', ...)`), but a failed attempt does not consume it. Known residual limitation: `state` isn't bound to a browser tab (login-CSRF risk) — real fix is authorization-code+PKCE, deliberately deferred.

**Tokens**: access 1h, refresh 7d, rotated on use + blacklisted after rotation (`ROTATE_REFRESH_TOKENS`/`BLACKLIST_AFTER_ROTATION`). `core/tokens.py:revoke_all_sessions(user)` blacklists every outstanding refresh token — called on password change/reset, and self-service via `POST /api/auth/logout-all/` (`LogoutAllSessionsView`). Live access tokens aren't individually revoked, just expire within the hour. `SECRET_KEY` and `JWT_SECRET_KEY` are two separate required secrets, no code fallback — app refuses to boot if either is unset.

**Password hashing**: BCryptSHA256 primary, PBKDF2 fallback verifier (`AUTH_PASSWORD_HASHERS`) — don't reorder without a migration plan. Policy enforced by `core/validators.py:StrongPasswordValidator` (upper/lower/digit/special) plus Django's stock validators, 128-char max.

**Admin user management** (`AdminUserDetailView`) — staff-gated (`is_staff`, not `is_superuser` — see admin-review-disputes.md for the authorization nuance). Granting/revoking `is_staff`/`is_active` requires the *acting admin's own current password* re-entered in the request body (`check_password`), and blocks an admin from removing their own `is_staff`/`is_active`. Every such change is logged to both `AuditLog` and `core/security_events.py`.

**Frontend**: `lib/api.js` (see frontend-infra.md) keeps the access token in memory only (`tokenStorage`, a plain module variable — never localStorage) and transparently refreshes on 401 via `POST /api/auth/token/refresh/`, which reads/rotates the refresh token from an httpOnly cookie (`esp_refresh`, `core/cookies.py`) rather than a request body — nothing refresh-token-shaped is ever readable from JS. `lib/appauth.jsx`'s `AppAuthProvider`/`useAuth()` `fetchMe()` attempts a silent `refreshToken()` call on mount whenever there's no in-memory access token (i.e. on every page reload for an already-logged-in user, since memory doesn't survive a reload) before falling back to logged-out — this is what keeps "stay logged in across a reload" working under the memory-only design. `login`/`register`/`googleLogin`/`logout` all pass `{ withCredentials: true }` so the browser sends/accepts the cookie on those specific requests only. Google button flow: `startGoogleSignIn()` (`googleAuth.js`) → full-page redirect to `accounts.google.com` → `/auth/google/callback` (`googlecallback.jsx`, guest-only route) parses the fragment, checks the nonce claim client-side as defense-in-depth, hands off to `googleLogin()`/`routeAfterLogin()`. Both localhost and production callback URLs must be registered in Google Cloud Console under **Authorized redirect URIs** (separate field from Authorized JavaScript origins).

## Invariants & gotchas

- Email verification is structural (no `User` row exists until OTP succeeds), not a boolean flag that could be bypassed.
- Throttle scopes: `login`/`login_email` 10/min, `register` 20/hour, `email_action`/`email_action_email` 5/hour — defined in `config/settings.py:DEFAULT_THROTTLE_RATES`. Add new auth-adjacent throttled endpoints here, don't hardcode a rate. Per-email throttles (`core/throttling.py`) exist alongside per-IP specifically to stop credential stuffing/reset-mail-bombing distributed across many IPs against one account.
- `Organizer.user`/`Tournament.organizer` are `PROTECT` (not `CASCADE`) — an approved organizer cannot self-delete their account while they have tournaments on record (`core.views.ProtectedUserDeleteMixin` turns the `ProtectedError` into a 400).
- `cleanup_pending_registrations` management command (`core/management/commands/`) prunes abandoned `PendingRegistration` rows + their Cloudinary CNIC/company docs, default 7 days — not scheduled automatically, needs an external cron (see deployment-ops.md).
- Registration email failing to send (Brevo down) still returns `201` — signup succeeded, only the email delivery is degraded; don't turn that into a 500.
- `AdminUserListView` now paginates (`core.pagination.StandardResultsPagination`, 20/page) — `{count, next, previous, results}`, not a bare array. `adminusers.jsx` was already updated to read `data.results` and drive prev/next controls.

## Known edge cases

See `docs/EDGE_CASES.md`'s "Registration & email-OTP verification" and "Google OAuth" sections for the full list (two people racing the same email, replayed OAuth state, Google unreachable mid-login, etc.) before touching this flow — several non-obvious gaps were already found and fixed here.

## Change log

- 2026-08-30 — Production-hardening pass: migrated the refresh token from `localStorage` to an httpOnly cookie (`core/cookies.py`, `CookieTokenRefreshView` replacing SimpleJWT's stock `TokenRefreshView` at `/api/auth/token/refresh/`), and the access token from `localStorage` to an in-memory-only JS variable (`frontend/src/lib/api.js`). `LoginView`/`GoogleLoginView`/`LogoutView`/`LogoutAllSessionsView` all updated to set/clear the cookie instead of reading/returning `refresh` in the JSON body. Requires `CORS_ALLOW_CREDENTIALS = True` (was `False`) — see frontend-infra.md and `docs/SECURITY.md#jwt`. Also fixed two OTP-resend handlers (`auth.jsx`, `verifyemail.jsx`) that swallowed a failed resend silently (the latter falsely claimed success). See `docs/SECURITY.md#jwt` for the accepted residual CSRF-rotation risk this migration introduces.
- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/SECURITY.md`/`ARCHITECTURE.md`/`EDGE_CASES.md`. No code changes made.
