---
feature: deployment-ops
status: stable
last_updated: 2026-08-28
paths:
  - .github/workflows/
  - backend/entrypoint.sh
  - backend/Dockerfile
  - docker-compose.yml
  - frontend/vercel.json
  - frontend/nginx.conf
  - backend/config/settings.py
related_docs:
  - docs/OPERATIONS.md
  - docs/SECURITY_CHECKLIST.md
  - docs/ARCHITECTURE.md#deployment-architecture
---

# Deployment & operations (CI/CD, hosting, incident history)

## What it does

Not a product feature — the deploy pipeline and production operational behavior. Kept as its own memory file because several past incidents here are non-obvious and easy to silently reintroduce.

## How it works

```
git push → GitHub Actions CI (ci.yml): Django tests (real Postgres container), frontend lint/typecheck/build
    ↓ (main only, CI must pass)
GitHub Actions Deploy job (deploy.yml): protected "production" environment, manual approval gate
    ↓
curl → Render deploy hook  +  curl → Vercel deploy hook
    ↓
Render rebuilds backend Docker image / Vercel rebuilds frontend, each on its own pipeline
```

GitHub Actions never builds/pushes a Docker image itself — only pings the two deploy hooks (`RENDER_DEPLOY_HOOK_URL`/`VERCEL_DEPLOY_HOOK_URL` repo secrets). Exactly **one** environment (production) — no staging deploy exists.

**Every container boot** runs `backend/entrypoint.sh`: `migrate --noinput` → `collectstatic --noinput` → `exec gunicorn`. `set -e` means a migration failure stops the boot entirely (Render reports a failed deploy, not a running-but-broken one) — if the backend is serving any traffic at all, migrations already succeeded for that boot.

## Known incidents — read before touching Render config, Dockerfile CMD, or settings.py fail-loud checks

- **Render "Docker Command" override silently bypasses `entrypoint.sh`.** A dashboard-level override (Settings → Deploy → Docker Command) replaces *both* `CMD` and `ENTRYPOINT` — this happened for real and meant migrations silently never ran on any deploy, indefinitely, no error anywhere. Symptom: `relation "X" does not exist` for an obviously-migrated table. Check that field is empty before chasing anything else.
- **`BREVO_API_KEY` unset in production surfaces as a misleading `DATABASES is improperly configured` error** when it fires during `entrypoint.sh`'s `migrate --noinput` step (Django's management-command bootstrapping partially swallows the real `ImproperlyConfigured`). The deploy still correctly fails — check `BREVO_API_KEY`/`SECRET_KEY`/`JWT_SECRET_KEY` first whenever you see the DATABASES error, before assuming the connection string is wrong.
- **The worker-boot crash loop** (fully diagnosed, three stacked causes, all fixed in code — see rag-chat.md's "Invariants & gotchas" for the code-level fix): eager model loading at import time + `--workers 3` on a 512MB instance + a slow CPU-bound model load exceeding gunicorn's `--timeout 120`. Fixed via lazy model loading + `--workers 1`. If it recurs, `python -c "import django; django.setup(); import rag_chat.urls"` timed should be ~3s, not longer.
- **Render env var changes don't reliably trigger an automatic redeploy** — use Manual Deploy → Deploy latest commit after editing an env var.
- **`ALLOWED_HOSTS` missing the real Render domain** → `DisallowedHost` on every request. Has shipped misconfigured before.
- **CI's `GROQ_API_KEY: ci-test-groq-key`** and **`SECURE_SSL_REDIRECT`/`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE: "False"`** in `ci.yml`'s backend-tests job are both load-bearing, not incidental: removing the Groq key breaks every test at import (see rag-chat.md); removing the security-cookie overrides causes ~150 unrelated-looking test failures because `SecurityMiddleware` 301-redirects every Django test-client request when `DEBUG=False` and these are unset (the test client doesn't follow redirects) — this exact failure mode has happened before.
- **Health check** (`/api/health/` and `/api/core/health/`, same view, `AllowAny`, no DB/external-service call): `.github/workflows/health-check.yml` pings every 5 min (best-effort — real gaps of 20-30 min observed, a GitHub Actions scheduler limitation, not a workflow bug) as a Render free-tier keep-alive. An isolated failed run is expected noise; only several *consecutive* failures indicate a real outage.

## Invariants & gotchas

- No background job queue exists anywhere (no Celery/RQ/django-q) — every "job-like" operation (email, Cloudinary/Groq/Chroma calls) runs synchronously inline in the request/response cycle. Don't assume something is queued/retried in the background; it isn't.
- No caching layer configured (no Redis/Memcached `CACHES`, no `@cache_page`) — the only cache-adjacent thing is DRF throttle counters using Django's default `LocMemCache`, which is **per-process** without `REDIS_URL` set (effective rate = configured rate × worker/instance count). Set `REDIS_URL` in production.
- Two unscheduled cleanup commands exist but nothing runs them automatically: `flushexpiredtokens` (SimpleJWT's own) and `cleanup_pending_registrations` (this repo's) — both need an external Render Cron Job.
- `Manual Deploy → Deploy latest commit` and dashboard settings changes (Docker Command, env vars) are the two most common sources of "the code is right but production is wrong" — check the dashboard before assuming a code bug.

## Change log

- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/OPERATIONS.md`/`ARCHITECTURE.md`. No code changes made.
