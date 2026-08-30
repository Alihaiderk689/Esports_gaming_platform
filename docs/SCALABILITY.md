# Scalability

What actually limits how much traffic/load this system can take today, and what changes first if it needs to take more. Companion to [`ARCHITECTURE.md`](ARCHITECTURE.md) (why the system is shaped this way) and [`OPERATIONS.md`](OPERATIONS.md) (how it runs and fails in practice) — this file is specifically about capacity, not correctness or day-to-day failure diagnosis.

## Current deployment shape

One Render web service (free tier: **0.1 vCPU, 512MB RAM**), `gunicorn --workers 1` (`backend/Dockerfile`), one Postgres database, one Vercel frontend deployment. No load balancer, no additional app instances, no read replica — everything this app does today runs through that single process. See `docs/OPERATIONS.md`'s "worker-boot crash loop" section for the specific incident (eager model loading + `--workers 3` + a 512MB instance) that already proved this instance size has a real ceiling.

`--workers 1` is not an arbitrary choice left over from debugging — the RAG pipeline's embedding model and cross-encoder reranker are lazily loaded per-worker-process (`rag_chat/services/embedding_service.py`, `rerank_service.py`), so each additional worker means another full in-memory copy of both models. On a 512MB instance, that's the real cap on worker count, independent of CPU.

## No background job queue

**None exists** (`docs/ARCHITECTURE.md`'s "Background jobs" section — no Celery/RQ/django-q, zero `@shared_task`/`.delay(`/`apply_async` call sites). Every operation that looks job-like runs synchronously inline in the request/response cycle:

- Sending email (Brevo API call) — verification OTPs, password resets, announcements, reschedule notices, tournament-win emails.
- Cloudinary uploads/deletes — organizer documents, tournament media, dispute evidence.
- The full RAG pipeline on every chat message — embed → vector search + keyword search (concurrent, but still synchronous from the request's point of view) → rerank → Groq generation.

This means request latency for these endpoints is bounded below by the slowest external dependency in the call, and a burst of announcement emails to many recipients (`send_announcement_emails`) ties up a worker for the whole loop, per-recipient exception handling notwithstanding. There is also **no automatic retry** anywhere in the backend (`docs/OPERATIONS.md`'s "Known operational limitations") — every external call (Brevo, Cloudinary, Groq, Chroma, Google cert verification) is a single attempt with a timeout.

At current traffic this is a deliberate, documented trade-off, not an oversight — but it's the first thing that needs to change if request volume or recipient-list sizes grow: move these onto a real queue (Celery/RQ) so a slow or failing external call no longer blocks the request that triggered it, and add retry/backoff (e.g. `tenacity`) around each external call.

## Caching

**No application cache backend is configured by default** (`docs/ARCHITECTURE.md`'s "Caching" section — no `CACHES` setting, no `@cache_page`, no view/query caching anywhere). `REDIS_URL` (`config/settings.py`) is optional and, when set, is wired up for exactly one purpose: giving DRF's throttle counters (`ScopedRateThrottle`/`UserRateThrottle`/`AnonRateThrottle`) a shared backend across processes.

Without `REDIS_URL` set, throttle counters fall back to Django's default `LocMemCache`, which is **per-process** — behind `gunicorn -w N` or multiple Render instances, the *effective* rate limit becomes `(configured rate) × (worker count)`, not the configured rate. This is a correctness gap today (rates in `config/settings.py`: `user: 1000/min`, `anon: 200/min`, plus scoped rates for login/register/chat/etc.) that becomes a real abuse-surface gap the moment worker count > 1, which running more workers to handle more load would directly cause. **Setting `REDIS_URL` in production is a prerequisite for scaling workers, not just a nice-to-have.**

There is no read-through cache for anything else — the game catalog, tournament listings, dashboard aggregates, and RAG retrieval results are all recomputed from Postgres/Chroma on every request. Read-heavy, rarely-changing data (the `games` catalog, published tournament listings) is the obvious first candidate if request volume grows enough to make repeated queries a bottleneck.

## Database

Single `DATABASES['default']` connection (`docs/ARCHITECTURE.md`'s "Database design" section), environment-switched between `DATABASE_URL_DEV`/`DATABASE_URL_PROD`. No connection pooler is bundled or configured by this repo itself — `config/settings.py` only defensively strips a `pgbouncer` query param if the production `DATABASE_URL` already sits behind one upstream (e.g. Supabase's pooled connection string), so a pooler can be added at the infrastructure level without a code change, but nothing here manages connection pooling on its own. No read replica exists; every read and write goes to the same instance.

**`brackets/services.py`'s lock ordering is a deliberate scalability trade-off, not an oversight**: every multi-lock transaction (result submission, bracket generation) takes a `Tournament` row lock first, which means result submissions for a *single tournament* serialize on that row. The module's own docstring states this explicitly as acceptable because "results for a single tournament are low-frequency and each transaction is short." This holds today; it would stop holding if a future feature pushed high-frequency concurrent match completions within one tournament (e.g. live bulk score imports) — see `docs/ARCHITECTURE.md`'s "Concurrency rules" section before touching this locking at all.

No Row Level Security — every access-control decision happens at the Django/DRF layer, so read/write scaling isn't complicated by a database-level policy layer, but also isn't helped by one.

## Static/media

Static files are served by Whitenoise from the same process serving the API (`docs/ARCHITECTURE.md`'s "Deployment architecture" section) — fine at current traffic, but it's request-handling capacity shared with the API itself, not offloaded to a CDN in front of the app. Media (uploads) already goes through Cloudinary in production, not local disk, so that half is already externalized and scales independently of the app server.

## Free-tier platform ceiling

Render's free tier sleeps the instance after a period of inactivity; the next request pays a 30-60+ second cold-start cost (`docs/OPERATIONS.md`'s "Health checks" section documents a keep-alive workflow that only partially mitigates this, since GitHub's own cron scheduling isn't reliable enough to guarantee the ping lands before idle-sleep triggers). This is a availability/latency ceiling independent of code changes — moving off the free tier removes it entirely and is a prerequisite for consistent response times under any real load, separate from every other item on this page.

## Summary: what to change, in the order it would actually bite

1. **Set `REDIS_URL` in production** before increasing `--workers` past 1 — otherwise scaling workers directly breaks the throttle rate guarantees.
2. **Move off Render's free tier** — removes the cold-start ceiling and the 512MB constraint that currently caps worker count via the RAG models' per-process memory footprint.
3. **Add a task queue** (Celery/RQ) for email sends and Cloudinary/Groq/Chroma calls — decouples slow external dependencies from request latency, and is a prerequisite for adding retry logic without also blocking the request thread.
4. **Add a connection pooler** (PgBouncer) if concurrent Postgres connections become the limit — the codebase already tolerates one sitting upstream (the `pgbouncer` param stripping in `config/settings.py`), so this is an infrastructure change, not a code change.
5. **Revisit the per-tournament lock serialization** in `brackets/services.py` only if a real feature needs high-frequency concurrent match completions within a single tournament — not before, since the module's current design deliberately trades that off for a provable deadlock-free lock ordering.
