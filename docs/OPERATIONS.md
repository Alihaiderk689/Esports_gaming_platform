# Operations

How Esports Pakistan actually runs in production, and how to diagnose it when something breaks. Every failure mode below either happened for real during this project's own operation, or is a direct, verified consequence of how the code is actually written — nothing here is generic "check your logs" advice. Companion to [`ARCHITECTURE.md`](ARCHITECTURE.md) (why the system is shaped this way), [`SECURITY_CHECKLIST.md`](SECURITY_CHECKLIST.md) (pre-deploy checklist), and [`ERROR_HANDLING.md`](ERROR_HANDLING.md) (how exceptions actually propagate).

## Deployment pipeline

```
git push → GitHub Actions CI (.github/workflows/ci.yml)
    ↓ (main branch only, CI must pass)
GitHub Actions Deploy job (.github/workflows/deploy.yml) — protected "production"
environment, manual approval gate
    ↓
curl → Render deploy hook  +  curl → Vercel deploy hook
    ↓
Render rebuilds the backend Docker image from the pushed commit
Vercel rebuilds the frontend from the pushed commit
```

**GitHub Actions never builds or pushes a Docker image itself** — `deploy.yml` only fires two webhook URLs (`RENDER_DEPLOY_HOOK_URL`/`VERCEL_DEPLOY_HOOK_URL` repo secrets) and each platform's own pipeline does the actual rebuild independently, on its own timeline. A green "Deploy" workflow run in GitHub only means the hooks were *called*, not that Render/Vercel finished (or even started) building yet — check each platform's own dashboard for the real build/deploy status.

**There is exactly one environment (production)** — no staging deploy exists anywhere in this pipeline. `ci.yml` runs on every push/PR to any branch; `deploy.yml` only fires on push to `main`.

### What happens inside the backend container on every boot

`backend/entrypoint.sh` (the Docker image's `ENTRYPOINT`) runs, in order, on **every single container boot** — not a one-time migration step someone runs by hand:

```sh
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"   # gunicorn, from the image's CMD
```

`set -e` means if `migrate` fails for any reason, the script exits immediately and gunicorn **never starts** — the container fails to boot at all, which Render reports as a failed deploy (not a running-but-broken one). This is important for diagnosis: if the backend is actually serving traffic (even broken traffic), migrations already ran successfully for that boot.

**A real incident**: the Render service was, for a period, configured with a **Docker Command override** (Render's dashboard field for replacing the image's `CMD`/`ENTRYPOINT` — Settings → Deploy → Docker Command) set to run `gunicorn` directly. Per Render's own semantics, a Docker Command override replaces *both* `CMD` and `ENTRYPOINT`, which meant `entrypoint.sh` — and therefore `migrate`/`collectstatic` — **silently never ran on any deploy**, indefinitely, with no error surfaced anywhere. The service just kept serving whatever schema state the database already happened to be in. **Symptom**: `django.db.utils.ProgrammingError: relation "X" does not exist` for a table/column that very obviously exists in a recent migration file. **Where to look**: Render dashboard → the service → **Settings → Deploy → Docker Command** — if it's non-empty, that's overriding the Dockerfile's own boot sequence. **Fix**: clear the override so the image's own `ENTRYPOINT`/`CMD` runs.

### `manage.py check` runs on every deploy too

Because `migrate` runs Django's system checks by default, `core/checks.py:production_monitoring_check` (registered via `core/apps.py`'s `ready()`) fires on every single deploy, not just when someone remembers to run `manage.py check --deploy` by hand. It emits (advisory only, doesn't block the deploy):
- `core.W001` — `REDIS_URL` unset in production (throttling silently degrades to per-process counters).
- `core.W002` — `SENTRY_DSN` unset in production (no error monitoring configured).

**Where to look**: these two warnings print near the top of the deploy log, right before the `Operations to perform:` / `Running migrations:` block. If you're scanning a deploy log for problems, they're easy to mistake for the actual failure — they're advisory, the app boots fine either way.

## Environment configuration failures (fail loudly, by design)

Two settings-load-time checks in `config/settings.py` deliberately **refuse to start the app at all** rather than run in a silently-broken state:

| Missing/wrong | What happens | Where it fires |
|---|---|---|
| `SECRET_KEY` or `JWT_SECRET_KEY` unset | `env('SECRET_KEY')`/`env('JWT_SECRET_KEY')` raise `django.core.exceptions.ImproperlyConfigured` immediately — no fallback value exists in code | Any `manage.py` invocation, including `migrate` |
| `BREVO_API_KEY` unset **and** `ENVIRONMENT=production` | Explicit `raise ImproperlyConfigured(...)` right after `ENVIRONMENT` is read (`config/settings.py` line ~211) | Same — including `entrypoint.sh`'s `migrate --noinput` step |

**A real incident, and the specific diagnostic trap it causes**: when the `BREVO_API_KEY` check fires *during* `entrypoint.sh`'s `migrate --noinput` step, Django's management-command bootstrapping partially swallows the real `ImproperlyConfigured` exception and surfaces a **confusing, unrelated-looking** downstream error instead — `django.core.exceptions.ImproperlyConfigured: settings.DATABASES is improperly configured` (as if the *database* were misconfigured, when the actual problem is a missing email API key that has nothing to do with the database). The deploy still correctly fails either way — this is a diagnostic-clarity problem, not a correctness one.

**Symptom**: deploy log shows `settings.DATABASES is improperly configured`, and it's tempting to go check `DATABASE_URL_PROD`/Postgres credentials first.
**Actual cause, confirmed directly**: raw `import config.wsgi` (gunicorn's real boot path, bypassing `manage.py`'s command-bootstrapping wrapper) shows the *real* message immediately — `BREVO_API_KEY is not set in production — ...`. **Action**: whenever you see the DATABASES error on deploy, check `BREVO_API_KEY` (and `SECRET_KEY`/`JWT_SECRET_KEY`) first, before assuming the database connection string is wrong.

## Health checks

Two endpoints resolve to the exact same view (`core.views.health_check`), returning `{"status": "ok"}`, `AllowAny`, no auth: `/api/health/` and `/api/core/health/` (`core/urls.py`). Both are deliberately lightweight — no database query, no external service call — so a failure of *this specific endpoint* means the process itself can't respond at all, not that some downstream dependency is degraded.

**Consumers of these endpoints**:
- `.github/workflows/health-check.yml` — pings `/api/core/health/` on a `schedule: cron: "*/5 * * * *"` (plus `workflow_dispatch` for manual runs), primarily as a Render free-tier keep-alive (prevents the idle-sleep cold start). **The `*/5` cron is a request, not a guarantee**: GitHub documents scheduled workflows as best-effort, and comparing consecutive run timestamps in the Actions tab shows real gaps of 20-30 minutes in practice — well past Render's ~15-minute idle-sleep threshold. That means the backend genuinely does spin down between pings sometimes, no matter how tight the cron string is; this is a GitHub Actions scheduler limitation, not something a workflow file can force. Given that, the `curl` call is budgeted generously (`--max-time 40 --retry 5 --retry-delay 10 --retry-max-time 300`, ~290s worst case) so a ping that does land on a cold instance has time to actually outlast the wake-up. **An isolated failed run is expected noise, not an incident** — only several *consecutive* failed scheduled runs point at a real outage. Requires the repo variable `PRODUCTION_BACKEND_URL` (Settings → Secrets and variables → Actions → Variables) — **not** a secret, since it's just the same base URL the frontend already calls publicly.
- `docker-compose.yml`'s `backend` service healthcheck — `curl`s the same `/api/health/` locally, with `depends_on: condition: service_healthy` gating the `frontend` container from starting until it passes.

**A real incident this endpoint's own simplicity couldn't protect against**: `config/urls.py` mounts every app's URLs (including `rag_chat.urls`) in one flat `urlpatterns` list. Resolving *any* URL — including this trivial health check — forces Django to import the *entire* URL module chain, which used to include `rag_chat/services/embedding_service.py` and `rerank_service.py` loading their `sentence-transformers`/`CrossEncoder` models **at module import time**. On a CPU-constrained instance, that load was slow enough to exceed gunicorn's worker timeout before the worker ever finished booting — so even this "lightweight" endpoint was, in practice, coupled to a multi-second-to-minutes ML model load happening somewhere else in the app entirely. See "RAG pipeline failures" below for the fix. **Lesson**: a health check being logically simple doesn't make it immune to unrelated heavy code sharing its import path — check what a URL resolution actually has to import, not just what the endpoint's own view does.

**Symptom checklist for a failing health check**:
1. `curl` (or the GitHub Actions job) shows `curl: (28) Operation timed out` with **zero bytes received**, not a fast HTTP error → the TCP/TLS connection succeeds but nothing ever answers → the process is up but stuck (see the crash-loop section below), or genuinely down.
2. A fast non-2xx response (404, 503) → the process answered; something more specific is wrong (wrong URL configured, or a real application-level failure).
3. `GitHub Actions → Backend Health Check → Ping /api/core/health/ → Check PRODUCTION_BACKEND_URL is configured` step failed → the repo variable itself is missing or empty, not a backend problem at all.
4. That same check step *passed* but the actual `curl` step fails fast (not a timeout) → the configured `PRODUCTION_BACKEND_URL` likely points at the wrong domain (verify it matches the exact Render service URL — this project's own workflow file was, at one point, configured against a placeholder domain from an earlier draft rather than the real one).

## The worker-boot crash loop (a real, fully-diagnosed incident)

This is the single most involved incident in this project's operational history, worth documenting as a complete symptom → cause → fix chain rather than as separate bullet points:

**Symptom**: every request — health check included — either hangs until a client-side timeout, or the Render log shows a boot/kill/reboot cycle repeating forever:

```
[INFO] Booting worker with pid: N
   ... (long gap)
[CRITICAL] WORKER TIMEOUT (pid:N)
[ERROR] Worker (pid:N) was sent SIGKILL! Perhaps out of memory?
[INFO] Booting worker with pid: N+1
   ... (repeats indefinitely)
```

**Root cause, layered** (all three contributed, found and fixed in this order):
1. `rerank_service.py`/`embedding_service.py` loaded their models **at module import time** (`model = CrossEncoder(...)`, `model = SentenceTransformer(...)`), and — as above — resolving *any* URL imports them via `config/urls.py`'s flat include chain.
2. `backend/Dockerfile`'s `CMD` originally hardcoded `--workers 3`. Each worker is a separate OS process with its own full copy of both models in memory — on a small (512MB) instance, three simultaneous copies was enough to trigger OOM kills under real request load, independent of the import-time issue.
3. On a CPU-constrained instance (Render's free tier: 0.1 vCPU), loading both models from scratch is slow enough that it can exceed gunicorn's `--timeout 120` before the worker ever finishes booting — gunicorn's master then assumes the worker has hung and sends `SIGKILL`, and the replacement worker hits the identical wall. **No request of any kind could ever be served, because none could complete before the timeout.**

**Fixes applied** (all live in code now):
- `backend/Dockerfile`'s `CMD` now uses `--workers 1` — matches what Render's platform-level `WEB_CONCURRENCY` default was already trying to signal, which the hardcoded `3` had been silently overriding.
- `rag_chat/services/embedding_service.py` and `rerank_service.py` now lazily instantiate their models on first actual use (a module-level cache behind a `_get_model()` accessor) instead of at import time — verified directly: importing the full URL chain now takes ~3 seconds with **zero** model loading; the RAG pipeline still works identically, it just pays the one-time load cost on the first real chat request instead of at every worker boot.
- `rag_chat/services/chunk_service.py` had its own `from rag_chat.services.embedding_service import model as _embedding_model` (a *direct* reference to the old eager-loaded object) — had to be updated to `_get_model()` too, or it would have silently re-introduced eager loading through its own import, since `views.py` imports `chunk_service` at module level as well.

**If this ever recurs** (e.g. a future change reintroduces an eager `SentenceTransformer(...)`/`CrossEncoder(...)` call at module level in any file reachable from `config/urls.py`'s import chain): the fastest confirmation is exactly what diagnosed it the first time — `python -c "import django; django.setup(); import rag_chat.urls"` timed with `time.time()` before/after; if it takes more than a second or two, something in that chain is doing real work at import time again, not just defining names.

## GitHub Actions / CI behavior

- **`ci.yml` runs on every push and PR to any branch** (not just `main`) via `on: push` / `on: pull_request` with no branch filter, plus `workflow_call` so `deploy.yml` can invoke it as a reusable job.
- **`secrets-guard`** hard-fails the build if any file matching `.env`/`.env.*` (other than `.env.example`) is tracked in git — a real gate, not just a reminder.
- **`backend-tests`** runs against a real ephemeral Postgres service container, with dummy secrets set as job-level env vars. Two specific env vars in that job are load-bearing in ways that aren't obvious from a failure alone:
  - `GROQ_API_KEY: ci-test-groq-key` — `rag_chat/services/groq_service.py` constructs a `Groq` client **at module import time**. Its absence breaks `manage.py test` at the *import* stage, before a single test runs, regardless of whether any test actually exercises Groq. **Symptom if ever removed**: every single test fails/errors, with an import-time traceback pointing at `groq_service.py`, not at whatever test happened to run first.
  - `SECURE_SSL_REDIRECT: "False"` / `SESSION_COOKIE_SECURE: "False"` / `CSRF_COOKIE_SECURE: "False"` — these three default to `not DEBUG` in `settings.py`, and CI sets `DEBUG: "False"`. Left unset, `SecurityMiddleware` 301-redirects every request the Django test client makes (the test client doesn't follow redirects by default). **Symptom if ever removed**: roughly 150 unrelated-looking test failures/errors across every app at once, not an obvious single cause — this exact failure mode has happened before in this project.
- **`container-scan` (Trivy)** runs filesystem-mode scans on every push/PR, `exit-code: 0` (report-only, deliberately — a dependency tree this size will surface an existing backlog the first time it runs; see `SECURITY_CHECKLIST.md`'s phased rollout plan for when to flip this to blocking).
- **`health-check.yml` failing does not block `deploy.yml` or `ci.yml`** — it's an intentionally separate workflow with its own trigger (`schedule`/`workflow_dispatch`), so a keep-alive ping failing never blocks a real deploy, and a deploy changing never affects the health-check schedule.

## Render/Vercel-specific gotchas

- **Render env var changes don't reliably trigger an automatic redeploy.** After editing an environment variable in Render's dashboard, use **Manual Deploy → Deploy latest commit** to actually pick it up — this has bitten real deploys before (a corrected `BREVO_API_KEY` sitting in the dashboard doing nothing until a manual redeploy actually restarted the process with it in the environment).
- **`ALLOWED_HOSTS` must include the actual Render domain.** Omitting it causes `DisallowedHost` on *every single request* — this has shipped misconfigured before.
- **`DEBUG` must be `False` in production**, and must be verified explicitly rather than assumed — `.env.example` ships `DEBUG=True` for local dev convenience, and the code default is `False` only if the env var is entirely unset, not if it's explicitly set to something truthy left over from a copy-paste.
- **A custom "Docker Command" in Render's dashboard silently overrides the image's own `ENTRYPOINT`/`CMD`** — see the crash-loop and migration sections above. This is the single most consequential Render dashboard setting in this project's operational history, precisely because it fails silently (the deploy "succeeds," the container "runs," it's just running the wrong boot sequence).
- **Vercel** serves the frontend; `frontend/vercel.json` sets security headers (`Content-Security-Policy: frame-ancestors 'none'`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) and `Strict-Transport-Security` at the header level (correct, since Vercel terminates TLS) — verify with `curl -I` against the real production URL after any frontend config change, since a CDN/proxy in front can silently strip headers it doesn't recognize.

## Database issues

- **Encryption in transit**: `config/settings.py` sets `sslmode=require` on `DATABASE_URL_PROD`'s parsed connection options whenever `ENVIRONMENT == 'production'`, unless the URL already specifies its own `sslmode`/`ssl` param (in which case that value is left alone). Before this existed, a `DATABASE_URL_PROD` without an explicit `sslmode` param connected over plaintext with nothing anywhere raising a flag.
- **A `pgbouncer` connection-string param is defensively stripped** (`_db_options.pop('pgbouncer', None)`) if the production `DATABASE_URL` sits behind a pooler (e.g. Supabase's pooled connection string) — Django's own DB backend doesn't understand that query param, and would otherwise error on connect. No pooler is bundled or configured *by* this repo itself; this only handles one that already exists upstream of it.
- **No Row Level Security** — every access-control decision happens at the Django/DRF layer, not the database. A migration or raw SQL issue is a data-integrity problem exactly as visible/debuggable as any other Django app; there's no separate database-level policy layer to also check.
- **Migration state drift** (Django's `django_migrations` bookkeeping disagreeing with what tables actually exist) is the other realistic cause of a `relation "X" does not exist` error, distinct from the Docker Command override above — check `python manage.py showmigrations <app>` (via Render's Shell tab, a paid feature; alternatively, trigger a fresh deploy and read the `migrate` output live in the Logs tab, which is free and shows exactly what ran).

## Brevo email failures

Every transactional email (verification OTP, password reset, announcements, reschedule notices, tournament-win) goes through `core/email_backend.py:BrevoAPIBackend`. `_send_one` logs a distinct, specific message *before* raising — `'Brevo API unreachable sending to %s...'` for a network/DNS/timeout failure reaching `api.brevo.com` at all, `'Brevo API rejected an email to %s...: HTTP %s — %s'` for a non-2xx response — so the cause can be told apart by scanning the log message text (see [`ERROR_HANDLING.md`](ERROR_HANDLING.md) for the full audit). `send_messages`'s own `logger.exception('Failed to send email via Brevo...')` still fires as well (it wraps every send), so both lines show up together — the specific one above it is what to scan for first.

| What the log shows | Likely cause | Action |
|---|---|---|
| `Brevo API unreachable sending to [...]: ...` | Network/DNS/timeout reaching `api.brevo.com` | Usually transient; if persistent, check Brevo's own status page |
| `Brevo API rejected an email to [...]: HTTP 400 — ...` | Almost always an **unverified sender** — Brevo rejects sends from a `DEFAULT_FROM_EMAIL` that isn't a confirmed sender in that Brevo account | Brevo dashboard → Senders & IP → verify the sender address |
| `Brevo API rejected an email to [...]: HTTP 401 — ...` | `BREVO_API_KEY` is wrong/revoked | Check the key in Render's Environment tab against Brevo's dashboard |
| No log line at all, but users report no emails | The request never reached this code — check `ENVIRONMENT`/`BREVO_API_KEY` are actually set (see the fail-loud settings check above); if `BREVO_API_KEY` is unset in a *non-production* `ENVIRONMENT`, `EMAIL_BACKEND` silently falls back to Django's console backend and prints the email body to stdout instead of sending | Confirm `ENVIRONMENT=production` is actually set, not just `BREVO_API_KEY` |

**Verifying a real deploy can actually send** (from `SECURITY.md`, repeated here as the operational procedure): trigger `POST /api/auth/resend-verification/` or `POST /api/auth/forgot-password/` with a real email → check the recipient's inbox → independently check Brevo's dashboard **Transactional → Email Activity** (confirms the request reached Brevo regardless of inbox delivery/spam-filtering) → if nothing shows in Brevo's activity log at all, the request never left the backend — check Render's logs for the `logger.exception` traceback above.

## Google OAuth issues

- **`GoogleAuthUnavailable` (503)** vs a plain `400 ValidationError` — deliberately different: a `GoogleAuthError` (network failure reaching Google's cert-verification servers) is a 503; a bad/expired/wrong-audience `id_token` (a `ValueError` from `google.oauth2.id_token.verify_oauth2_token`) is a 400. If Google sign-in is failing for *everyone* at once, check for a 503 pattern in the logs (network-level, likely transient) before assuming a token/config problem.
- **`GOOGLE_CLIENT_ID` mismatch** between backend and frontend is a real, checklist-flagged failure mode — `GOOGLE_CLIENT_ID` (backend env var) must match `VITE_GOOGLE_CLIENT_ID` (frontend build-time env var) exactly, or every token verification fails with a wrong-audience `ValueError` → 400.
- **Redirect URI not registered** — the production frontend's `/auth/google/callback` path must be registered in Google Cloud Console under **Authorized redirect URIs** specifically (a separate field from Authorized JavaScript origins, which only takes bare origins). Symptom: Google itself shows an error page before the app's own code ever runs, so this isn't visible in this project's own logs at all — it's a Google Cloud Console configuration check, not a backend debugging problem.
- **`google_login.invalid_token`/`.nonce_mismatch`/`.unverified_email` security events** (`core/security_events.py`, `core/views.py:GoogleLoginView`) are exactly what to search Render's logs for to see the *specific* reason a Google login failed — the raw exception message from Google's library is logged via `logger.warning`, since `verify_oauth2_token` raises a bare `ValueError` for every distinct failure mode with no subclass to tell them apart otherwise.

## RAG pipeline / Groq / Chroma / model-loading failures

- **A deprecated/removed Groq model** (a real incident, now fixed): `GROQ_MODEL` in `.env.example`/`backend/.env.example` and `rag_chat/services/groq_service.py`'s own fallback default (used only if `GROQ_MODEL` is ever completely unset) were both `llama-3.3-70b-versatile`/`llama-3.1-8b-instant` at the time — both confirmed removed from Groq's available models entirely. **Symptom, if it recurs with some future model deprecation**: every single chat request fails with `groq.NotFoundError: 404 - The model does not exist or you do not have access to it`, regardless of question content or which game was involved. Both are now `openai/gpt-oss-120b` — but this is an external vendor decision Groq can make again with no advance warning in this codebase, so **always verify the actual deployed `GROQ_MODEL` value in Render's Environment tab** rather than assuming it matches `.env.example`. **Where to look**: `python manage.py ask "<question>"` reproduces this directly from a terminal, no HTTP/auth needed, and shows the real traceback instead of the generic `503` the API returns. **Verifying available models**: `GET https://api.groq.com/openai/v1/models` with the real `GROQ_API_KEY` as a Bearer token lists exactly what's currently servable — do this periodically, not just when something breaks.
- **The eager-model-loading crash loop** — see its own section above; this is the same underlying RAG code, but the symptom there is "nothing responds at all," not "chat specifically errors."
- **Chroma Cloud's own rate/quota limits**: a `get()` call with a large `limit` can hit `chromadb.errors.ChromaError: Quota exceeded: ... exceeds limit of 300` — Chroma Cloud's free/default tier caps how many records a single `Get` action can return. `chroma_service.py`'s own `query()`/`keyword_query()` calls stay well under this (`n_results`/`limit` defaults of 20/10/5), but any ad-hoc diagnostic script (e.g. checking how many chunks exist for a given game) needs to paginate with `offset`/`limit` rather than requesting everything in one call.
- **A rulebook PDF's content ends up tagged under the wrong game, or under no game at all** — `chunk_service.py` doesn't use whichever `Game` catalog entry the admin selected in the upload UI; it splits the document at `"1. Introduction"` boundaries and runs `game_detector.detect_game()` independently on each section's own text. A single upload can legitimately produce chunks for several different games (verified directly against this project's own corpus — one upload nominally filed under one catalog game produced correctly-tagged content for seven different games) — or, if a section's text doesn't clearly name any known game, chunks with `game_name=""`, which never match a scoped query and are effectively invisible to the chatbot until content is re-uploaded with clearer per-section game references.
- **"I can only answer questions related to esports rules and the uploaded documents"** for a question about a real, supported game is expected behavior, not a bug, whenever no rulebook has actually been uploaded for that game yet — check what games currently have chunks in the Chroma collection (see the quota note above for how to check this safely) before assuming the retrieval/generation pipeline itself is broken.

## Cloudinary issues

- **Every upload failure surfaces as a `503 StorageUnavailable`**, not a silent failure or a generic 500 — `core/storage.py:CloudinarySignedStorage` wraps every Cloudinary SDK call (`_save`, `delete`, `exists`, `size`, `get_created_time`) in a broad `except Exception: logger.exception(...); raise StorageUnavailable()`. **Symptom**: any document upload (organizer CNIC/company docs, tournament compliance documents, payment proofs, dispute evidence) returns 503 instead of the expected 200/201. **Where to look**: `logger.exception` in the Render logs shows the real underlying Cloudinary SDK error (auth failure, quota, network) — the 503 itself carries no detail about *why* by design (a generic "temporarily unavailable" message to the client), so the actual cause always requires checking the server-side log line, not the API response.
- **`CLOUDINARY_CLOUD_NAME`/`_API_KEY`/`_API_SECRET` unset or wrong** turns every single upload into this same 503 pattern — verify these three are actually set in Render's Environment tab, since there's no equivalent fail-loud startup check for them the way `BREVO_API_KEY`/`SECRET_KEY` get (Cloudinary's own client library doesn't validate credentials at configure-time, only when an actual API call is made).
- **Rulebook PDF uploads go through a *different*, unwrapped path** (`rag_chat/services/cloudinary_service.py`) than the signed-storage documents above — no `StorageUnavailable` wrapping exists there, so a Cloudinary failure during rulebook upload propagates as a raw exception, caught one layer up by `RuleBookUploadView`'s own broad `except Exception` (see [`ERROR_HANDLING.md`](ERROR_HANDLING.md)) rather than by the storage layer itself.

## Known operational limitations

- **No background job queue exists** (no Celery/RQ/django-q) — every operation that looks job-like (sending email, calling Cloudinary/Groq/Chroma) runs synchronously, inline, in the request/response cycle. A slow external dependency directly slows down the request that triggered it; there is no async retry or dead-letter queue for a failed send to be picked up later automatically.
- **No automatic retry logic anywhere in the backend** — every external HTTP call (Brevo, Cloudinary, Groq, Chroma, Google's cert verification) is a single attempt with a timeout, no `tenacity`/backoff wrapper. The only place an automatic retry exists at all is the GitHub Actions health-check workflow's own `curl --retry 5` flags — infrastructure-level, not application code. Design compensates for this via idempotency (a retried client request is often a safe no-op — see `EDGE_CASES.md`'s duplicate-`AdminReviewRequest`/OTP-resend entries) rather than the backend retrying on the caller's behalf.
- **Token blacklist cleanup is unscheduled by default** — `python manage.py flushexpiredtokens` (ships with `djangorestframework-simplejwt`) exists and works, but nothing in this repo runs it automatically; it needs an external scheduler (a Render Cron Job) — see `SECURITY_CHECKLIST.md`'s "Token blacklist cleanup" section. `python manage.py cleanup_pending_registrations` (`core/management/commands/`) is the same situation: it exists and works (deletes stale `PendingRegistration` rows and their Cloudinary documents — see `ERROR_HANDLING.md`'s "Swallowed / partial-failure exceptions" section), but nothing schedules it either, so abandoned signups still accumulate until someone (or something) actually runs it.
- **Free-tier Render specifics**: 0.1 vCPU, 512MB RAM, and the platform sleeps the instance after a period of inactivity (cold start can take 30-60+ seconds on the next request, sometimes longer — see "Health checks" above for a real observed case). The health-check workflow's ping exists specifically to prevent that sleep from ever triggering, but its `*/5` cron is a request GitHub doesn't reliably honor (real gaps of 20-30 minutes observed) — so cold starts still happen periodically regardless of the schedule string, and that's expected, not a misconfiguration to chase. If the workflow is ever unscheduled entirely or the `PRODUCTION_BACKEND_URL` variable becomes stale, cold starts will become the norm rather than the occasional exception.
- **Log aggregation is "whatever Render's own log viewer shows"** unless `SENTRY_DSN` is set — there is no external log aggregator configured in this repo. Render's log search has its own retention/time-window limits (its search box scopes to a selectable time range, e.g. "Last hour"), which can make an older incident's logs unreachable through search alone if the window has rolled past it — widen the time range or search by the specific error text rather than assuming "no results" means "didn't happen."
