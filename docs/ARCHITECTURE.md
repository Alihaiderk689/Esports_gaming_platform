# Architecture

This explains *why* Esports Pakistan is built the way it is — the layers, the data flow, and the rules that hold the system together. For "how do I run this" / "where is X", see [`CLAUDE.md`](../CLAUDE.md). For "what protects user data", see [`docs/SECURITY.md`](SECURITY.md).

## Layers

```
React (frontend/)
    ↓  fetch, JWT bearer token
Django REST Framework views  (views.py per app)
    ↓
Service layer                 (only some apps — see below)
    ↓
Django ORM
    ↓
PostgreSQL
```

This is the intended shape, but it's only fully real in two apps. Whether an app has a service layer tells you something about how much stateful, multi-step logic it owns:

| App | Service layer | Why |
|---|---|---|
| `brackets` | `services.py` (~1500 lines) | Bracket generation/progression is a graph-construction problem with real invariants (no fabricated players, no player eliminated on one loss in double elim, deterministic seeding) — it needs to exist independent of any one view. |
| `tourny_regist` | `lifecycle.py` + `validation.py` + `emails.py` | Tournament/registration/team state transitions (submit, cancel, reschedule, duplicate, lock/unlock/substitute) need to be callable identically from the organizer's self-service endpoint *and* the admin-approval endpoint — see [Admin-review escalation](#admin-review-escalation) below. `lifecycle.py`'s own docstring states this explicitly. |
| `rag_chat` | `services/` package (9 modules) | The RAG pipeline (upload → chunk → embed → retrieve → rerank → generate) is a multi-stage process with real external dependencies at each stage. |
| `games`, `partners`, `dashboard`, `organizer`, `core` | none | Logic lives directly in `views.py`/`serializers.py`. These apps are mostly CRUD-shaped or read-only aggregation; there's no multi-step invariant to protect, so a service layer would be indirection without payoff. |

Don't add a `services.py` to an app just for consistency — add one when a view starts needing to share non-trivial logic with another view, an admin path, or a background process. `organizer`'s approval flow and `core`'s auth views are flat today because nothing yet requires the same mutation from two different call sites; `tourny_regist` grew one specifically because the admin-review path does.

## Authentication architecture

Stateless, bearer-token JWT (`djangorestframework-simplejwt`) — no session-cookie auth class is registered for the API (`config/settings.py`, `DEFAULT_AUTHENTICATION_CLASSES`). Three entry points converge on the same token-issuing step:

1. **Password login** (`core/views.py:LoginView`) — email + password, then issues a JWT pair.
2. **Google OAuth** (`core/views.py:GoogleLoginView`) — client does an OAuth2 implicit-flow redirect (not GIS `renderButton()`), gets an `id_token` from Google directly in the URL fragment, POSTs *only that token* to this endpoint. The backend verifies it against Google's public certs via `google.oauth2.id_token.verify_oauth2_token(...)`, checks `email_verified`, `get_or_create`s the `User` by email (backfilling `google_id` onto a pre-existing password account with a matching, Google-verified email), then issues the same kind of JWT pair as password login.
3. **Email-verified registration** (`core/models.py:PendingRegistration` → `core/views.py:VerifyEmailView`) — signup does **not** create a `User`. It creates a `PendingRegistration` row (hashed password, not plaintext) and emails a signed token. Only when that link is clicked does `VerifyEmailView` create the real `User` (and `Organizer`, if applicable) inside one transaction, then delete the pending row. No click, no account — this is enforced structurally, not by a flag that could be bypassed.

Access tokens live 1 hour; refresh tokens 7 days, rotated on use with the old one blacklisted (`ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`). Password change and password reset both call `core/tokens.py:revoke_all_sessions(user)`, which blacklists every outstanding refresh token for that user — a stolen refresh token stops working the moment the real owner changes their password. Live access tokens aren't individually revoked this way; they simply expire within the hour.

Full detail: [`docs/SECURITY.md#authentication`](SECURITY.md#authentication).

## Authorization architecture

Two mechanisms, applied consistently across apps that need object-level checks:

- **`permissions.py` classes** (`tourny_regist`, `games`, `partners`) — the pattern to follow for a new object-level check: staff always passes; otherwise compare `request.user` (or `request.user.organizer_profile`) against the object's owner FK. `tourny_regist.permissions.IsTournamentStaffOrAdmin` is the one most other object checks in the codebase are modeled on.
- **Direct `IsAdminUser` on views** — used wherever the entire view is staff-only with no object-level nuance (every `Admin*View` across `core`, `tourny_regist`, `organizer`, `dashboard`, `rag_chat`).

**Admin-review escalation** is the load-bearing authorization pattern in this codebase, and it's the same shape in three unrelated places:

```
Organizer attempts a dangerous action (cancel tournament / cancel registration / reset bracket)
    ↓
Is it safe? (no registrations yet / no bracket yet / no real results yet)
    ├── yes → execute immediately, self-service
    └── no  → raise NeedsAdminReview
                  ↓
              View catches it, creates an AdminReviewRequest, returns 202
                  ↓
              Admin later approves/rejects via AdminReviewRequestDecideView
                  ↓
              On approval: re-call the *same* service function with bypass_safety_check=True
```

`NeedsAdminReview` exists as two separate classes (`tourny_regist.lifecycle.NeedsAdminReview` and `brackets.services.NeedsAdminReview`), matched structurally by the catching view rather than a shared base — deliberate, so `tourny_regist` doesn't need to import `brackets` just to catch its exception. The point of this pattern: approval never "replays" the action generically. Each `request_type` (`TOURNAMENT_CANCELLATION`, `REGISTRATION_CANCELLATION`, `BRACKET_RESET`) is handled by an explicit branch in `AdminReviewRequestDecideView`, which calls the exact same function the safe path would have called — so there's exactly one code path per dangerous action, not a self-service one and a separate admin one that could drift apart.

## Database design

PostgreSQL, one `DATABASES['default']` connection, environment-switched between `DATABASE_URL_DEV`/`DATABASE_URL_PROD` via `ENVIRONMENT`. No Row Level Security — every access-control decision (ownership checks, staff gating) happens at the Django/DRF layer, not the database layer. A `pgbouncer` key is defensively stripped from parsed connection options (`config/settings.py`) for compatibility if the production `DATABASE_URL` sits behind a pooler; no pooler is bundled or configured in this repo itself.

Key model relationships:
- `core.User` — custom, email as `USERNAME_FIELD`, no `username` field.
- `organizer.Organizer` — `OneToOneField` on `User`. Approval workflow: `pending` → `approved`/`rejected`.
- `tourny_regist.Tournament` — owned by an `Organizer`; separate `status` (draft/pending/approved/rejected/cancelled) and `is_published` (visibility) axes — a tournament can be admin-approved but still hidden until the organizer publishes it.
- `tourny_regist.Registration` — one per player per tournament; `checked_in` gates bracket eligibility; `seed` (nullable) is an optional manual override consumed by `brackets.services.seed_players` ahead of the registration-order fallback.
- `tourny_regist.Team`/`TeamMembership` — team-based tournaments, joined via `invite_code`; `is_locked` freezes self-service join/leave once competitive activity starts (only staff can unlock or substitute a member after that point).
- `brackets.Bracket`/`Match` — `Match` nodes route forward via `next_match`/`next_match_slot` (winner path) and `loser_next_match`/`loser_next_match_slot` (loser path). This pointer-graph design is what let the bracket engine be generalized to arbitrary (non-power-of-two) participant counts without changing the schema — see `brackets/services.py`'s module docstring for the seeding/bye/losers-bracket algorithm.
- `core.AuditLog` — generic (`GenericForeignKey` `target`), written only through `core.audit.log_action(actor, action, target, reason, **metadata)`. Deliberately **not** globally browsable: the only read paths are `TeamHistoryView`/`RegistrationHistoryView`, each scoped to one object the requester already manages, specifically so it can't be used to enumerate audit entries for objects outside the requester's authority.
- `core.Dispute`/`DisputeEvidence` — `target` is a `GenericForeignKey` onto either a `Tournament` (general complaint) or a `Match` (result-specific), which is why `core` doesn't need to import `tourny_regist`/`brackets` for this model. `escalated_to_admin` moves resolution authority from "the tournament's own organizer" to "staff only" — for the specific case a dispute is *about* that organizer's own ruling.
- `core.AdminReviewRequest` — see [Authorization architecture](#authorization-architecture) above.

## Background jobs

**None exist.** No Celery, RQ, django-q, or any task queue is configured anywhere in this codebase — confirmed by an empty dependency list and zero `@shared_task`/`.delay(`/`apply_async` call sites. Every operation that looks job-like (sending email, calling Cloudinary/Groq/Chroma) runs synchronously inline in the request/response cycle. This is a real architectural property, not a gap being tracked: if a future feature needs a queue, it starts from zero, not from an underused existing one.

## External APIs

| Service | Used for | Where | Failure handling |
|---|---|---|---|
| **Cloudinary** | Sensitive document storage (CNIC scans, compliance docs, payment proofs) via `core/storage.py:CloudinarySignedStorage`; rulebook PDFs via `rag_chat/services/cloudinary_service.py` | `core.storage`, `rag_chat.services.cloudinary_service` | `core/storage.py` wraps every call and raises `StorageUnavailable` (503) on failure, logged first. The rulebook-PDF helper has no such wrapping — errors there propagate unhandled. |
| **Google OAuth** | Verifying Google-issued `id_token`s server-side | `core/views.py:GoogleLoginView`, via the `google-auth` library (not a hand-rolled REST call) | Bad/expired/wrong-audience token → 400; network failure reaching Google → distinct 503 (`GoogleAuthUnavailable`). |
| **Groq** | LLM inference for the RAG rules assistant | `rag_chat/services/groq_service.py` | Client is constructed **at module import time** — `GROQ_API_KEY` must be set (even to a dummy value) just to import the app, which is why CI sets a dummy key. No retry wrapper around the completion call itself. |
| **ChromaDB Cloud** | Vector store for rulebook chunk retrieval | `rag_chat/services/chroma_service.py` | Lazily connects on first use. Vector search and keyword search run concurrently (`ThreadPoolExecutor`) in `retrieval_service.py`, since each Chroma Cloud round trip costs ~200-250ms. No retry wrapper. |
| **sentence-transformers** | Local embedding model (`all-MiniLM-L6-v2`) — not a hosted API | `rag_chat/services/embedding_service.py`, loaded at import time | The Dockerfile pre-downloads this model (and the cross-encoder reranker) at *build* time and sets `HF_HUB_OFFLINE=1`, so gunicorn workers never hit HuggingFace Hub at runtime. CI caches the same models to avoid re-downloading every run. |
| **SMTP** | Verification/reset/reschedule emails | `core/emails.py`, `tourny_regist/emails.py` | Dev default is Django's console backend (prints to stdout, no real send). Production must set a real `EMAIL_BACKEND`/`EMAIL_HOST` — see the security checklist. |

## Caching

**None configured.** No `CACHES` setting, no `@cache_page`, no Redis/Memcached backend. The only cache-adjacent code is DRF's throttle counters, which use Django's implicit default (`LocMemCache`) purely as their storage — tests call `cache.clear()` between runs so throttle counts don't leak across test methods, but there is no application-level caching layer to reason about.

## Deployment architecture

```
git push → GitHub Actions CI (backend tests against real Postgres, frontend lint/typecheck/build)
    ↓ (main branch only, CI must pass)
GitHub Actions Deploy job (protected "production" environment — manual approval gate)
    ↓
curl → Render deploy hook  +  curl → Vercel deploy hook
    ↓
Render rebuilds/redeploys the backend from the pushed commit
Vercel rebuilds/redeploys the frontend from the pushed commit
```

There is exactly **one** environment target (production) — no separate staging deploy exists in the GitHub Actions workflows. GitHub Actions itself never builds or pushes a Docker image; it only pings the two platforms' deploy hooks and their own pipelines do the rebuild.

The backend Docker image's `entrypoint.sh` runs `python manage.py migrate --noinput` and `collectstatic --noinput` on **every container boot**, before the app process starts — migrations are not a separate manual step in this deployment. There's no DB-readiness wait loop in `entrypoint.sh` itself (Render is assumed already up); the local `docker-compose.yml` path does wait, via a Postgres healthcheck and `depends_on: condition: service_healthy`.

Static files are served by **Whitenoise** (`WhiteNoiseMiddleware`, positioned right after `SecurityMiddleware` per its own requirement), with `CompressedManifestStaticFilesStorage` for hashed/compressed assets. Media (in production) does not go through Whitenoise or local disk at all — it goes through Cloudinary; local disk (`MEDIA_ROOT`) is a dev-only fallback per `DEBUG`.

Render env var changes don't reliably trigger an automatic redeploy — a Manual Deploy is needed to actually pick up a changed variable. `ALLOWED_HOSTS`/`DEBUG=False` misconfiguration has shipped to production before (see the security checklist).

## Concurrency rules

This is the one place in the codebase where getting the architecture wrong has caused real, demonstrated bugs (a lost-update race in match completion, and a lock-ordering inversion between bracket generation and match completion) — so the rule is enforced by more than a comment.

**`brackets/services.py`** declares and enforces a total lock ordering, quoted here in full because paraphrasing it risks losing the reasoning:

> ```
> LOCK ORDER — Tournament, then Bracket, then Match.
>
> Every transaction in this module that takes more than one row lock takes them in
> that order, which makes deadlock impossible by construction rather than by argument:
> a cycle requires two transactions to acquire the same pair in opposite orders, and a
> single global ordering forbids that.
>
> The rule exists because the obvious implementation violates it. Match completion
> naturally wants to lock the match and then, once a result decides the event, the
> tournament (M -> T); bracket generation naturally locks the tournament and then
> completes newly-created bye matches (T -> M). Those two are an inversion. It happens
> not to deadlock today, because the matches generation locks are rows it created in
> its own uncommitted transaction and no other transaction can see or lock them — but
> that reasoning rests on row visibility and would quietly stop holding the moment a
> generator locked a pre-existing match. So `complete_match` takes the tournament lock
> first instead, and every entry point below follows suit.
>
> Re-locking a row already held by the same transaction is a no-op in PostgreSQL, so
> the redundant tournament lock in `finalize_tournament_champion` costs nothing when
> reached through match completion.
>
> The practical cost is that result submissions for one tournament serialize on its
> row. That is acceptable here — results for a single tournament are low-frequency and
> each transaction is short — and it is what buys a provable ordering.
>
> `_lock_tournament` is the only way this module takes a tournament lock; adding a new
> multi-lock path means starting from it. `tests.LockOrderAuditTests` fails if a
> `select_for_update()` appears anywhere in the engine that this rule has not accounted
> for.
> ```

`LockOrderAuditTests` (`brackets/tests.py`) statically parses `services.py`'s AST and fails the suite if a new `select_for_update()` call appears that isn't accounted for in the ordering — so this rule survives refactoring, not just review.

**`tourny_regist/lifecycle.py`** deliberately stays out of that ordering rather than trying to join it:

> ```
> Tournament lifecycle actions (submit/resubmit/cancel/reschedule/duplicate).
>
> Mirrors brackets/services.py's module-as-service-layer shape: business logic
> lives here, not in serializers or views, so both the organizer-facing view
> and the admin-approval path can call the exact same functions. Does not
> touch brackets/services.py or its lock order — see that module's LOCK ORDER
> note if a future stage needs to coordinate a Tournament lock with a Bracket
> lock; this module only ever locks the Tournament row.
> ```

**The rule for extending this**: if you're adding code that needs to lock more than one of {Tournament, Bracket, Match}, it belongs in `brackets/services.py` and must go through `_lock_tournament`/`_lock_bracket` in that order — don't invent a second, parallel locking scheme. If you only ever need to lock a `Tournament` row alone (as `tourny_regist/views.py` does for team-join/registration-capacity races), a local, single-row `select_for_update()` is fine and doesn't need to interact with the bracket engine's ordering at all — three such isolated single-row locks already exist in `tourny_regist/views.py` (team join by invite code, tournament registration-capacity check, admin-review-request double-decide guard).
