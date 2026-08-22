# Security checklist

Run through this before every production deploy — not just the first one. Several items here have shipped misconfigured before (noted where that's happened); this list exists because "it worked last time" isn't the same as "it's still correct now." See [`docs/SECURITY.md`](SECURITY.md) for *why* each of these matters and [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for how the system fits together.

## Core Django settings

- [ ] `DEBUG=False` in the production environment. (Code defaults to `False` if unset, but `.env.example` ships `True` for local dev — confirm the actual deployed value, don't assume the default.)
- [ ] `ALLOWED_HOSTS` includes the real production domain(s). **Has shipped wrong before** — omitting the Render domain causes `DisallowedHost` on every single request.
- [ ] `SECRET_KEY` is set, not committed, and is not the value from `.env.example`.
- [ ] `JWT_SECRET_KEY` is set, not committed, different from `SECRET_KEY`.
- [ ] `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` are left unset or `True` in production (they default to `not DEBUG`, so they're correct automatically *if* `DEBUG` is correctly `False` — but verify explicitly, since these have a documented CI failure mode when left inconsistent with `DEBUG`).
- [ ] `SECURE_HSTS_SECONDS`/`SECURE_HSTS_INCLUDE_SUBDOMAINS`/`SECURE_HSTS_PRELOAD` are at their production defaults (non-zero / `True`) — same `not DEBUG` caveat as above.

## CORS / CSRF

- [ ] `CORS_ORIGINS` is set to the real frontend origin(s) only — not the `localhost:5173` dev default.
- [x] `CORS_ALLOW_ALL_ORIGINS` is **not** introduced anywhere (it isn't used today; keep it that way). **Regression-tested**: `core/tests.py:SecuritySettingsInvariantTests.test_cors_does_not_allow_all_origins` fails CI if this ever gets set.
- [x] `CORS_ALLOW_CREDENTIALS` is still `False` (`config/settings.py`) — the frontend authenticates via bearer token, not cookies, so there's nothing legitimate for credentialed CORS to unlock. If a future feature genuinely needs cross-origin cookies, that's a deliberate design change, not a quick flip — think it through rather than just setting it back to `True`. **Regression-tested**: `test_cors_does_not_allow_credentials`.
- [ ] `CSRF_TRUSTED_ORIGINS` matches the real frontend origin(s) — relevant to Django admin, not the JWT API (see `docs/SECURITY.md#csrf`).

## Security headers / CSP

- [ ] The frontend's deployed origin (Vercel or self-hosted nginx) is actually serving `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Content-Security-Policy: frame-ancestors 'none'` — check with `curl -I` against the real production URL, not just that `frontend/vercel.json`/`frontend/nginx.conf` contain the config. A CDN/proxy in front of either can silently strip headers it doesn't recognize.
- [ ] `frontend/index.html`'s CSP `<meta>` tag's `img-src` names `https://res.cloudinary.com` explicitly plus a broader `https:` fallback (for cover images/game logos, which may be served from the production API origin rather than Cloudinary — see `docs/ARCHITECTURE.md`); `connect-src` stays broad since `VITE_API_URL` is environment-dependent. **Once the real production hostnames are fixed, narrow both to the exact origins** instead of the `https:` fallback — this wasn't done yet only because the exact deployed domain names weren't available to pin against.
- [ ] `Strict-Transport-Security` is only set where TLS is actually terminated (Vercel headers) — confirm it hasn't been added to `nginx.conf` if that container is ever exposed directly rather than behind a TLS-terminating proxy (see `docs/SECURITY.md#security-headers--csp`).

## Authentication

- [ ] `GOOGLE_CLIENT_ID` (backend) matches `VITE_GOOGLE_CLIENT_ID` (frontend) exactly.
- [ ] The production frontend's Google OAuth redirect URI is registered in Google Cloud Console under **Authorized redirect URIs** (a separate field from Authorized JavaScript origins — the former needs the full callback path, the latter only a bare origin).
- [ ] Rate limits on `login`/`login_email`/`register`/`email_action`/`email_action_email` scopes are unchanged from `config/settings.py`'s `DEFAULT_THROTTLE_RATES` — if they were loosened for local testing, confirm they weren't left loosened in a deployed config.
- [ ] `REDIS_URL` is set in production. Without it, throttling falls back to per-process `LocMemCache` — behind more than one gunicorn worker or instance, every rate limit above is effectively (configured rate) × (worker/instance count), not the configured rate. See `docs/SECURITY.md#rate-limiting`. **Now flagged automatically if missed**: `core/checks.py:production_monitoring_check` (registered in `core/apps.py`) emits `core.W001` when `ENVIRONMENT=production` and `REDIS_URL` is unset — visible in `manage.py check` output and, since `backend/entrypoint.sh` runs `migrate --noinput` before starting gunicorn (and `migrate` runs system checks by default), in every Render deploy log. Advisory only — it warns, it doesn't block the deploy, since the app still runs (just with less correct throttling).
- [x] `SIMPLE_JWT['ALGORITHM']` is still explicitly `'HS256'` in `config/settings.py` — don't let this get removed under the assumption "the library default is fine," since the point of pinning it is that a future change can't silently widen it. **Regression-tested**: `core/tests.py:SecuritySettingsInvariantTests.test_jwt_algorithm_is_pinned_to_hs256`.

## Authorization

- [ ] Every new admin-only endpoint uses `permissions.IsAdminUser` (or an equivalent explicit `is_staff` check) — remember this checks `is_staff`, not `is_superuser`; confirm that's actually the intended tier before adding a new one. Consider `core/admin_capabilities.py:HasAdminCapability(...)` instead of `IsAdminUser` directly if the new endpoint is a good candidate for the future granular-role rollout — it behaves identically today, so there's no cost to adopting it early (see `docs/SECURITY.md#authorization`).
- [ ] Every new endpoint returning or mutating a specific object enforces ownership server-side (compare `request.user`/`request.user.organizer_profile` against the object's owner FK) — never trust a client-supplied ID to imply authorization to act on it. For a **list** endpoint scoped to a parent object (e.g. "announcements for tournament X"), remember `check_object_permissions()` isn't called automatically the way it is for a single-object view — call it explicitly against the parent (see `TournamentAnnouncementsView.get_queryset()` for the pattern) or the list silently has no object-level gate at all, which is exactly the bug this checklist item exists because of (see `docs/SECURITY.md#idor-audit--two-real-gaps-found-and-fixed`).
- [ ] A serializer field that surfaces `some_user.email` (or falls back to it when a display name is blank) is only ever returned to that user themselves, staff, or another verified stakeholder — never to "any authenticated user" or the public. If in doubt, use the `display_name()` pattern in `brackets/serializers.py`/`tourny_regist/serializers.py` (falls back to `f'Player #{pk}'`/`f'User #{pk}'`, never an email).
- [ ] Any new "dangerous" organizer self-service action (deletes/cancels data that other users depend on) either has its own safety check, or is routed through the `NeedsAdminReview` → `AdminReviewRequest` escalation pattern rather than executing unconditionally. If it's implemented as a function in `lifecycle.py`/`services.py` rather than inline in the view, the safety check belongs *in that function*, not the view calling it — see `docs/SECURITY.md#service-layer-invariants`.
- [ ] Granting or revoking another user's `is_staff`/`is_active` still requires the acting admin's own `current_password` in the request body (`AdminUserDetailView.update`) — don't remove this to make an admin UI flow more convenient; it's the backstop against a stolen-but-still-valid access token being enough to mint or deactivate an admin account on its own.

## Secrets

- [x] No `.env` file (any environment) is committed. `.gitignore` covers `.env`/`.env.*`/`.env.local`. **CI-enforced**: `.github/workflows/ci.yml`'s `secrets-guard` job hard-fails the build if any file matching `.env`/`.env.*` other than `.env.example` is tracked in git — this used to be a "do a final git status scan" reminder, now it's a gate that can't be skipped by forgetting. (The `container-scan` Trivy job's `secret` scanner also covers this plus other secret patterns, but report-only — see Dependency scanning below.)
- [ ] `ANTHROPIC_API_KEY` — and any other secret read via `os.getenv`/`env()` — is actually present in the deployed environment. `ANTHROPIC_API_KEY` and `REDIS_URL` are now listed in both `.env.example` (root and `backend/`), but a new secret added later needs the same treatment — don't assume it'll be noticed otherwise.
- [ ] **`BREVO_API_KEY`** is set in production (Render env var) — email is sent via Brevo's transactional API (`core/email_backend.py`), not SMTP; there is no `EMAIL_HOST`/`EMAIL_HOST_PASSWORD` fallback anymore. **Enforced at settings-load time** (`config/settings.py`, right after `ENVIRONMENT` is read): raises `ImproperlyConfigured` if `ENVIRONMENT=production` and `BREVO_API_KEY` is unset — without it, `EMAIL_BACKEND` silently falls back to the console backend, which prints full email bodies (including password-reset links and email-verification codes) to stdout — same "refuse to start" treatment as `SECRET_KEY`/`JWT_SECRET_KEY` already get. Note: if this ever actually fires during `backend/entrypoint.sh`'s `migrate --noinput` step, Django's own management-command bootstrapping partially swallows the exception and surfaces a confusing downstream `settings.DATABASES is improperly configured` error instead of this check's clear message — the deploy still correctly fails either way (confirmed: raw `import config.wsgi`, gunicorn's actual boot path, shows the real message immediately), it's only the diagnostic clarity that's degraded on that one specific path. If you ever see that DATABASES error on deploy, check `BREVO_API_KEY` (and `SECRET_KEY`/`JWT_SECRET_KEY`) first before assuming the database is actually misconfigured.
- [ ] The Brevo account's sender address (whatever `DEFAULT_FROM_EMAIL` is set to) is a **verified sender** in Brevo's dashboard — Brevo's API rejects sends from an unverified sender address, which would surface as every email failing with a 400-range `RuntimeError` from `BrevoAPIBackend`, logged but not raised to the caller (announcement/reschedule emails swallow per-recipient failures by design — see `docs/SECURITY.md`). This fails silently from the user's perspective, so it's worth actually testing (see the verification steps in `docs/SECURITY.md`'s Brevo section), not just assuming it works because the key is set.
- [ ] The Brevo API key is scoped to transactional-email sending only in Brevo's dashboard (not a full-access key with account/contact-management permissions it doesn't need).
- [ ] No secret value appears in a log line, error message, or `AuditLog.metadata` — if you added a new `logger.exception`/`log_action` call, check what's actually being passed in.

## Admin surface

- [ ] Django admin (`/admin/`) is only reachable by staff who should have it — check `is_staff` assignments periodically, not just at rollout.
- [ ] No new model is registered in Django admin (`admin.py`) that exposes sensitive fields (password hashes, raw document contents, tokens) without deliberately restricting the admin's list/detail fieldsets.

## Database

- [ ] `DATABASE_URL_PROD` uses an encrypted connection. `config/settings.py` now enforces `sslmode=require` by default in production if the URL doesn't already specify one — confirm the effective connection is actually encrypted post-deploy (e.g. check your Postgres provider's connection log/dashboard), don't just trust the default silently did its job.
- [ ] Confirm there is still no reliance on database-level Row Level Security for anything security-critical — if that ever changes, this checklist (and `docs/SECURITY.md#database-security`) needs an update to match, since right now every reviewer's mental model is "the DRF layer is the *only* access-control layer."
- [ ] A new FK from a model with tournament-scale downstream data (registrations, brackets, disputes, ...) onto `User`/`Organizer` defaults to `PROTECT` or `SET_NULL`, not `CASCADE` — `CASCADE` on `Organizer.user`/`Tournament.organizer` used to let an organizer's self-service account deletion silently destroy every tournament they'd ever run (see `docs/SECURITY.md#account-deletion--data-integrity`). If a new model needs the same "the actor can go away, the record can't" property (disputes, review requests, and similar accountability records already follow this), use `null=True, blank=True, on_delete=models.SET_NULL`.

## Security monitoring

- [ ] `SENTRY_DSN` is set in production if Sentry monitoring is wanted (unset in dev/CI is correct — nothing is sent anywhere without it). If set, confirm events are actually arriving in the Sentry project post-deploy, not just that the env var is present. **Now flagged automatically if missed**: `core/checks.py:production_monitoring_check` emits `core.W002` when `ENVIRONMENT=production` and `SENTRY_DSN` is unset — same mechanism/visibility as the `REDIS_URL` check above. Advisory only, since Sentry is explicitly optional.
- [ ] A new `logger.exception`/`log_security_event`/`log_action` call doesn't pass a password, JWT, refresh/reset/verification token, OAuth `id_token`, or raw request body into its fields/metadata — same rule for all three of these, restated here because it's easy to reach for whichever one is closest at hand without re-checking.

## File uploads

- [ ] Cloudinary credentials (`CLOUDINARY_CLOUD_NAME`/`_API_KEY`/`_API_SECRET`) are set and valid in production — a missing/wrong credential turns every document upload into a 503, not a silent failure, but confirm this was actually tested post-deploy.
- [ ] If a new document-upload field is added anywhere, it goes through `validate_document_file` (or an equally strict content-sniffed validator) — don't accept a new upload type by trusting the client's declared `Content-Type` or filename extension. `validate_document_file` now actually decodes the file (Pillow for images, PyMuPDF for PDFs), not just sniffs magic bytes — if a new test fixture for this path starts failing after a Pillow/PyMuPDF version bump, check whether the fixture bytes are still genuinely decodable, not just correctly-prefixed.
- [ ] SVG is still excluded from accepted document formats (deliberate stored-XSS mitigation for the admin's `<iframe>` document preview) — don't add it back without addressing that risk directly.

## Rate limiting

- [ ] Every new auth-adjacent or otherwise abuse-prone endpoint has a `throttle_scope` set, using an existing scope from `DEFAULT_THROTTLE_RATES` where it fits, or a newly added scope in that same table — not a hardcoded rate inline in the view.
- [ ] A new endpoint that accepts an account identifier (email, username) in its body and is abuse-prone per-account (not just per-IP) considers a `core/throttling.py:PerFieldRateThrottle` subclass alongside its `ScopedRateThrottle`, the way `LoginView`/`ForgotPasswordView`/`ResendVerificationView` do — an IP-only limit doesn't stop an attack distributed across many IPs against one account.

## Scheduled cleanup

Neither of these runs automatically today — no Celery/RQ/task queue exists in this codebase (see `docs/ARCHITECTURE.md#background-jobs`), so "scheduled" means an external scheduler (a Render Cron Job, or `cron` directly) invoking a plain management command, not application code that fires on its own.

- [ ] `python manage.py flushexpiredtokens` (ships with `djangorestframework-simplejwt`) is scheduled to run periodically in production (e.g. a Render Cron Job). Without it, `OutstandingToken`/`BlacklistedToken` rows accumulate forever; this is a performance/storage concern, not an access-control one on its own, but worth catching before the table gets large enough to matter.
- [ ] `python manage.py cleanup_pending_registrations` (`core/management/commands/`) is scheduled alongside it — deletes `PendingRegistration` rows (abandoned email-OTP signups) older than 7 days by default (`--older-than-days` to adjust), along with any CNIC/company document already pushed to Cloudinary for an abandoned organizer signup. Run with `--dry-run` first against production to see what it would delete before scheduling it for real. Same non-issue as the token blacklist above: unscheduled, these just accumulate (storage growth), they don't leave anything accessible that shouldn't be.

## Dependency scanning

- [ ] `.github/dependabot.yml` is still present and its PRs aren't being ignored wholesale — a Dependabot config that nobody merges from is no better than not having one. Skim open Dependabot PRs periodically, especially for `django`, `djangorestframework-simplejwt`, `google-auth`, `pillow`, `PyMuPDF`, and `cloudinary`.
- [ ] `.github/workflows/ci.yml`'s `container-scan` job (Trivy) findings have actually been looked at, not just left green because `exit-code: 0` means it can't fail the build. Roll this out in phases rather than flipping straight to blocking (which risks becoming noisy enough that findings start getting ignored wholesale):
  1. **Report-only** (current state) — scan runs on every push/PR, nothing blocks.
  2. **Triage the existing backlog** — for each CRITICAL/HIGH finding, either upgrade the dependency, or consciously accept it (and record *why*, e.g. "no fix available yet, not reachable from user input").
  3. **Establish the accepted baseline** — what's left after triage is the known-accepted set, not unaddressed noise.
  4. **Flip to blocking** (`exit-code: 1`) for *new* CRITICAL/HIGH findings only, once the baseline is clean — a fresh finding from here on really does mean "something changed," not "the scanner found what it always finds."

## Logging

- [ ] `LOGGING`'s `django`/`core`/`rag_chat` console handlers are still wired (they're what makes 500 errors visible in Render's logs with `DEBUG=False` — Django's own default config only does this when `DEBUG=True`). If this was ever accidentally removed, production 500s go dark with no visibility.
- [ ] No new logging call captures request bodies, headers, or full user objects wholesale (risk of accidentally logging a password or token that was present in the payload).

## CI/CD-specific gotchas (verify these are still true, not just "were true once")

- [ ] `.github/workflows/ci.yml` still sets `GROQ_API_KEY` to a dummy value for the test job — `rag_chat/services/groq_service.py` builds its client at *import time*, so its absence breaks `manage.py test` before a single test runs, not just RAG-specific tests.
- [ ] `.github/workflows/ci.yml` still explicitly forces `SECURE_SSL_REDIRECT=False`/`SESSION_COOKIE_SECURE=False`/`CSRF_COOKIE_SECURE=False` for the test job. Without this, `DEBUG=False` in CI makes these default `True`, and `SecurityMiddleware` 301-redirects every request the Django test client makes (which doesn't follow redirects) — this has previously surfaced as ~150 unrelated-looking test failures instead of one obvious cause. If tests start failing in bulk with no clear pattern, check this first.
- [ ] Render env var changes were followed by a **Manual Deploy → Deploy latest commit** — Render does not reliably auto-redeploy on a bare env var change.

## Concurrency

- [ ] Any new code that takes more than one row lock across `Tournament`/`Bracket`/`Match` goes through `brackets/services.py`'s `_lock_tournament`/`_lock_bracket` helpers, in that order — see `docs/ARCHITECTURE.md#concurrency-rules`. `brackets/tests.py:LockOrderAuditTests` should catch a violation automatically, but don't rely on that alone if you're touching this area — read the module's LOCK ORDER comment first.
- [ ] Any new "check a count/capacity against a limit, then create a row if it's under" endpoint (registration caps, roster slots, and similar) locks the relevant parent row (`select_for_update()`) for the whole check-then-create sequence inside `transaction.atomic()` — see `RegistrationCreateView`/`TeamJoinView`/`TeamRegisterView` for the pattern, and `docs/SECURITY.md#concurrency` for the race this actually prevents. A capacity check with no lock at all reads correctly and still oversells the moment two requests land close together.
- [ ] Locking the object being *directly* touched isn't automatically enough — if a player can reach the same "am I already in state X" outcome through two *different* endpoints/objects (e.g. creating a new team vs. joining an existing one), the lock needs to be on whatever's shared between those paths (the `Tournament` row, for team formation — see `TeamCreateView`/`TeamJoinView`), not on the object each path happens to create/touch individually.
- [ ] A new `tourny_regist.lifecycle`/`brackets.services` function that enforces a safety invariant (something that must hold regardless of which view calls it) has a test that calls the function directly, not only a test that goes through the view — see `docs/SECURITY.md#service-layer-invariants`.

## Business logic / state machine

- [ ] A new state-changing endpoint or serializer `validate()`/`update()` explicitly checks which states the object may currently be in before acting — not just who's allowed to act. "Any authenticated stakeholder, any current state" is the exact shape every gap found in `docs/SECURITY.md#business-logic--state-machine-invariants` had in common; a permission class alone answers "who," never "when."
- [ ] Before assuming an inconsistency between two similar-looking serializers/views is a bug worth fixing uniformly, check the existing test suite for a test that *exercises* the asymmetry on purpose — `organizer/serializers.py:AdminOrganizerUpdateSerializer` intentionally allows re-deciding an already-rejected application directly (unlike its `tourny_regist` tournament-approval counterpart), and `organizer/tests.py:test_approve_clears_previous_rejection_reason` proves it's deliberate. Applying a "consistency fix" here would have been a real regression — see `docs/SECURITY.md`'s note in that section for the concrete near-miss.
- [ ] A new "self-service destructive action" (delete/withdraw/leave, initiated by the object's own owner rather than an organizer/admin) checks whether the object has already entered a shared, bracket/match-connected state before allowing an unconditional hard delete — see `RegistrationDeleteView`'s `hasattr(tournament, 'bracket')` guard. A player's own DELETE/POST shouldn't be able to orphan another player's live match.
- [ ] If two lifecycle-request-creating endpoints (a "request admin review" pattern) can be retried/double-clicked, prefer a partial `UniqueConstraint` (`condition=models.Q(status='pending')` or similar) over trusting the view alone not to be called twice — see `core/models.py:AdminReviewRequest.Meta` and the `except IntegrityError` pattern at each of its three call sites (`TournamentCancelView`/`RegistrationCancelView`/`TournamentBracketResetView`).
