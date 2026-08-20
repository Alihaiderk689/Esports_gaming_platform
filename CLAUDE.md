# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Esports Pakistan — a full-stack esports tournament platform. Organizers host verified tournaments across Valorant, Tekken 8, Counter-Strike 2, PUBG Mobile, and EA Sports FC; players register, get seeded into brackets, and compete. Includes an AI rules assistant (RAG over uploaded rulebook PDFs) that answers rulebook questions per-game.

Backend: Django 4.2 + DRF, PostgreSQL, JWT auth (`djangorestframework-simplejwt`), Cloudinary media storage.
Frontend: React + Vite, React Router, Tailwind CSS, shadcn/ui ("new-york" style), Framer Motion.
RAG assistant: PyMuPDF (PDF extraction), `sentence-transformers` (embeddings), ChromaDB Cloud (vector store), Groq (LLM inference).

## Further documentation

This file covers day-to-day rules and gotchas. For the details behind them:

- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — why the system is shaped the way it is: the service-layer pattern (and which apps do/don't have one), authentication/authorization architecture, database design, external API integrations, deployment pipeline, and — importantly — the bracket engine's lock-ordering rules. Read this before touching `brackets/services.py`'s locking, or before deciding whether a new app needs its own `services.py`.
- **[`docs/SECURITY.md`](docs/SECURITY.md)** — how auth, authorization, data isolation, CSRF/CORS, rate limiting, secrets, and file uploads actually work today. Read this before modifying anything under `core/views.py`'s auth endpoints, any `permissions.py`, or `core/storage.py`.
- **[`docs/SECURITY_CHECKLIST.md`](docs/SECURITY_CHECKLIST.md)** — run through this before every production deploy, not just the first one.

## Commands

### Backend (`backend/`)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in secrets — see Environment below
python manage.py migrate
python manage.py runserver
```

Run all tests: `python manage.py test`
Run one app's tests: `python manage.py test brackets` (also: `core`, `games`, `organizer`, `tourny_regist`, `partners`, `rag_chat`)
Run a single test case/method: `python manage.py test brackets.tests.BracketServiceTests.test_generate_bracket`
Make/apply migrations after model changes: `python manage.py makemigrations && python manage.py migrate`

RAG assistant debugging (no HTTP/auth needed):
- `python manage.py ask "How many players are in a PUBG match?"` — runs the full retrieval → rerank → generate pipeline from the terminal.
- `python manage.py evaluate_rag` — runs the fixed `EVAL_CASES` regression set (retrieval substring checks + RAGAS scoring) against the live rulebook corpus.
- `python manage.py eval_retrieval` — retrieval-only evaluation.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
npm run dev          # Vite dev server, expects backend at VITE_API_URL (default http://localhost:8000)
npm run build
npm run lint          # eslint . --quiet
npm run lint:fix
npm run typecheck    # tsc -p ./jsconfig.json — JS files under checkJs, not a TS project
```

There is no frontend test runner configured (no test script in `package.json`).

## Architecture

### Backend: app boundaries

Each Django app under `backend/` owns its own `models.py` / `serializers.py` / `views.py` / `urls.py`, all mounted under `/api/` in `config/urls.py`. Cross-app relationships to know about:

- **`core`** — the custom `User` model (`AUTH_USER_MODEL = 'core.User'`, email as `USERNAME_FIELD`, no username field), auth views (register/login/Google login/logout/JWT refresh/password reset/email verification), player listing/profile/follow endpoints, and admin user management. `core.validators.StrongPasswordValidator` is wired into `AUTH_PASSWORD_VALIDATORS`.
- **`organizer`** — `Organizer` is a `OneToOneField` on `User` (`user.organizer_profile`), created via an application (company info, CNIC, payout method) that goes through admin approval (`Organizer.Status`: pending/approved/rejected). `IsApprovedOrganizer` (in `tourny_regist/permissions.py`) gates tournament creation on this status.
- **`games`** — the game catalog (Valorant, Tekken 8, CS2, PUBG Mobile, EA Sports FC, etc.) that `tourny_regist.Tournament` and `rag_chat` rulebooks both key off of by name/slug.
- **`tourny_regist`** — the core domain: `Tournament` (approval workflow mirrors `Organizer`'s pending/approved/rejected, plus a separate `is_published` flag gating public visibility), `Team`/`TeamMembership` (for team-based tournaments, joined via `invite_code`), `Registration` (one per player per tournament, `checked_in` flag determines bracket eligibility), and `Announcement`. Permission classes here (`IsTournamentStaffOrAdmin`, `IsPublicOrOwner`, `IsApprovedOrganizer`) are the pattern to follow for new object-level checks: staff always passes, otherwise compare against `request.user.organizer_profile` or `created_by`.
- **`brackets`** — bracket generation and progression, decoupled from `tourny_regist` via a plain `tournament` FK. `Match` nodes link forward via `next_match`/`next_match_slot` (winner path) and `loser_next_match`/`loser_next_match_slot` (loser path, used by double elimination). `services.py` is the important file here — see below.
- **`partners`** — sponsor/partner listings.
- **`dashboard`** — read-only aggregate stats.
- **`rag_chat`** — rulebook upload + AI chat assistant, see below.

Media uploads (organizer CNIC/company docs, tournament covers/certificates, payment proofs) are served from `MEDIA_ROOT` only when `DEBUG=True`; in production they're expected to go through Cloudinary. The dev-only media route in `config/urls.py` is deliberately exempted from `X_FRAME_OPTIONS` (via `xframe_options_exempt`) so the admin UI can preview uploaded documents in an `<iframe>`, and wrapped in `never_cache` to avoid a stale cached 403 from before that exemption existed.

### Bracket generation (`backend/brackets/services.py`)

All formats pull players from `tournament.registrations.filter(checked_in=True)`, ordered by registration time — that ordering *is* the seeding rank (best seed = registered first). Each `generate_*_bracket(tournament)` function is a pure builder that creates `Bracket` + `Match` rows and returns the `Bracket`:

- **Single elimination** (`generate_bracket` / `_build_single_elim`) — pads the field to the next power of two using standard bracket seeding (`_seed_order`/`_seed_slots`) so byes land on top seeds first, then auto-completes bye matches immediately via `complete_match`.
- **Double elimination** / **3-game guarantee** (`generate_double_elimination_bracket`, `generate_three_game_guarantee_bracket`) — both share `_build_double_elim_core`, which builds the winners bracket then threads losers into a losers bracket via `_pair_losers` (seed round) and `_drop_in` (subsequent rounds' WB losers merging with LB survivors). 3-game guarantee is the double-elim core plus one extra bonus match (`Match.Side.GUARANTEE`) for players eliminated from both brackets in round 1. Both require the player count to be an exact power of two (double-elim: ≥4; guarantee3: ≥8) — this is enforced with a `ValidationError`, not silently rounded.
- **Round robin** (`generate_round_robin_bracket` / `_round_robin_rounds`) — standard circle-method scheduler.
- **Swiss** (`generate_swiss_bracket`, `generate_next_swiss_round`) — round 1 pairs by registration order; later rounds pair by current `standings()` and avoid rematches where possible (`_have_played`), falling back to allowing one if pairing would otherwise get stuck. Rounds are generated one at a time on demand, not all upfront — `generate_next_swiss_round` refuses to advance until every match in the current round is `COMPLETED`.
- **Group stage + playoff** (`generate_group_playoff_bracket` then `generate_group_playoff_bracket_phase2`) — two explicit phases. Phase 1 splits players into round-robin groups; phase 2 (called separately once group play finishes) takes the top standing from each group and feeds them into `_build_single_elim`.
- `complete_match(match, winner, score)` is the single place that advances a winner (and loser, for double-elim-style brackets) into whatever match its `next_match`/`loser_next_match` pointers reference, flipping that match to `READY` once both slots are filled. Any new bracket format should still terminate in matches wired through these same pointers so `complete_match` keeps working unmodified.
- `standings(tournament, players=None)` ranks by completed-match win count, ties broken by original registration order — used both for the public standings view and internally to seed the next Swiss round / pick group qualifiers.

### RAG rules assistant (`backend/rag_chat/`)

Pipeline, in order, across `services/`:
1. **Upload** — admin uploads a rulebook PDF for a specific game (`pdf_service.py` extracts text via PyMuPDF).
2. **Chunk + tag** — `chunk_service.py` splits into per-section chunks; `game_detector.py` tags each chunk (and later, each incoming question) with a detected game name.
3. **Embed + store** — `embedding_service.py` (sentence-transformers) embeds chunks into ChromaDB Cloud (`chroma_service.py`).
4. **Retrieve** — `retrieval_service.retrieve_candidates(question, fallback_game=...)` runs vector search and keyword search *concurrently* (`ThreadPoolExecutor`) since each Chroma Cloud round trip costs ~200-250ms; merges and dedupes results. `fallback_game` carries the previous turn's detected game forward so follow-up questions that don't name a game (e.g. "what about substitutes?") stay scoped instead of searching unscoped across every game.
5. **Rerank** — `rerank_service.py` reranks the merged candidates.
6. **Generate** — `prompt_service.build_context()` assembles the reranked chunks into a prompt; `groq_service.generate_answer()` calls Groq, grounded only in retrieved text (it's instructed not to answer beyond what's in the uploaded rulebooks).

`cloudinary_service.py` handles rulebook PDF storage. Chat turns are persisted as `ChatHistory` (see `models.py`) so `fallback_game` context-carrying works across a conversation.

When changing retrieval/reranking/prompting, use `python manage.py ask "<question>"` for a quick manual check and `python manage.py evaluate_rag` to check the fixed regression set in `evaluate_rag.py`'s `EVAL_CASES` before assuming it still works — those substrings are verified against the actual uploaded rulebook text, not guessed, so a real regression will fail the substring check even if the answer still "reads" fine.

### Frontend structure

- **`src/lib/api.js`** — single fetch-based API client (`api.get/post/patch/put/delete`). Handles JWT storage in `localStorage` (`esp_token`/`esp_refresh`) and transparent access-token refresh on a 401 via `/api/auth/token/refresh/`, retrying the original request once. DRF validation error shapes (`{field: ["reason"]}` with no `detail`/`message` wrapper) are flattened into a single error message string.
- **`src/lib/appauth.jsx`** — `AppAuthProvider`/`useAuth()`, the auth context wrapping the whole app. Fetches `/api/auth/me/` on mount if a token exists; exposes `login`, `register`, `googleLogin`, `logout`, `refreshUser`.
- **Route guards** (`src/lib/*route.jsx`) — composed as nested `<Route>` wrappers in `App.jsx`, not per-page checks: `ProtectedRoute` (must be authenticated), `GuestRoute` (guest-only, e.g. `/login`), `AdminRoute` (staff only), `NotAdminRoute` (redirects staff away from the player-facing app shell), `OrganizerOrAdminRoute` (gates organizer-only pages like `/players`, `/create`, `/my-tournaments`, `/tournaments/:id/edit`). Admin pages live under a separate `AdminLayout` at `/admin/*`; player/organizer pages live under `AppLayout`.
- **`src/pages/`** — one file per route, wired up explicitly in `App.jsx` (no file-based routing).
- **`src/components/ui/`** — shadcn/ui primitives (style: "new-york", base color: neutral, icon library: lucide). Regenerate/add via the shadcn CLI rather than hand-rolling new primitives; it's configured in `components.json`.
- Path alias `@/*` → `src/*` (set in both `vite.config.js` and `jsconfig.json`).
- `jsconfig.json`'s `include` covers `src/components/**/*.js`, `src/pages/**/*.jsx`, `src/Layout.jsx`, and `src/vite-env.d.ts`. Its `exclude` lists `src/components/ui`, `src/lib`, and `src/api`, but that only keeps those directories from being *root* files — `tsc` still type-checks their contents whenever an included file imports them (which is most of them), so `npm run typecheck` errors can and do surface inside "excluded" files too. Don't assume a file is unchecked just because it's under one of these paths.

**Google sign-in** (`src/pages/auth.jsx`, `src/lib/googleAuth.js`, `src/pages/googlecallback.jsx`) — a plain OAuth 2.0 implicit-flow redirect, not GIS's `renderButton()`. Clicking the button calls `startGoogleSignIn()` (`googleAuth.js`), which stores a nonce in `sessionStorage` and does a full-page `window.location.href` to `accounts.google.com`'s `/o/oauth2/v2/auth` with `response_type=id_token`. Google redirects back to `/auth/google/callback` (`googlecallback.jsx`, guest-only route) with the token in the URL *fragment* (`#id_token=...`, never sent to any server) — `consumeGoogleCallback()` parses it, checks the nonce claim client-side as defense-in-depth, then hands off to the same `googleLogin()`/`routeAfterLogin()` (`src/lib/routeAfterLogin.js`) path form-based login uses. This replaced an earlier iframe/`renderButton()` approach that broke for ad-blocker users and was never fully reliable in Chrome; the backend (`core.views.GoogleLoginView`) is unchanged either way — it always just verified a bare `id_token`. Both `http://localhost:5173/auth/google/callback` and the production equivalent must be registered in Google Cloud Console under **Authorized redirect URIs** (a separate field from Authorized JavaScript origins — the latter takes bare origins only, the former takes full paths).

## Environment

Backend needs `backend/.env` (copy from `.env.example`): `SECRET_KEY`/`JWT_SECRET_KEY`, `DATABASE_URL_DEV`/`DATABASE_URL_PROD` (switched on `ENVIRONMENT`), Cloudinary creds, `CHROMA_API_KEY`/`CHROMA_TENANT`/`CHROMA_DATABASE`, `GROQ_API_KEY`/`GROQ_MODEL`, `GOOGLE_CLIENT_ID`, and SMTP settings for verification/reset emails (use an app password, not a real account password).

Frontend needs `frontend/.env`: `VITE_API_URL`, `VITE_GOOGLE_CLIENT_ID` (must match the backend's `GOOGLE_CLIENT_ID`).

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR: Django tests (against a real Postgres service container) and frontend lint/typecheck/build. `deploy.yml` fires Render + Vercel deploy hooks on push to `main`, gated behind CI passing and a protected `production` GitHub Environment (manual approval) — needs `RENDER_DEPLOY_HOOK_URL`/`VERCEL_DEPLOY_HOOK_URL` repo secrets to actually deploy anything.

CI's Django job sets `GROQ_API_KEY` to a dummy value even though no test calls Groq directly — `rag_chat/services/groq_service.py` constructs a `Groq` client at *module import time*, so its absence breaks `python manage.py test` at the import stage before any test runs. It also explicitly sets `SECURE_SSL_REDIRECT`/`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` to `False` — these default to `not DEBUG` in `settings.py`, and with `DEBUG=False` in CI, an unset `SECURE_SSL_REDIRECT` made `SecurityMiddleware` 301-redirect every request the Django test client made (which doesn't follow redirects), turning into ~150 unrelated-looking test failures instead of one obvious cause. If either of these env vars ever goes missing from `ci.yml` again, that's the failure mode to expect.

Backend deploys (Render) need `ALLOWED_HOSTS` to include the actual Render domain and `DEBUG=False` — both have shipped misconfigured before (`DisallowedHost` on every request; a live `DEBUG=True` leaking full tracebacks publicly). Render env var changes don't reliably trigger an automatic redeploy — after editing them, use Manual Deploy → Deploy latest commit to actually pick them up.

## Notes specific to this codebase

- DRF throttle scopes are pre-defined in `config/settings.py` (`login`: 10/min, `register`: 20/hour, `email_action`: 5/hour) — new auth-adjacent views that need throttling should reuse `ScopedRateThrottle` with one of these scopes or add a new one there, not hardcode a rate inline.
- Password hashing is BCryptSHA256 first, PBKDF2 as fallback (`AUTH_PASSWORD_HASHERS`) — don't reorder this without a migration plan for existing hashes.
- `config/settings.py` filters two specific third-party warnings (urllib3/OpenSSL, google-auth FutureWarning) at the top of the file, before other imports — this ordering is load-bearing because those imports happen transitively via `INSTALLED_APPS`, not because of import style preference.
- `LOGGING` in `settings.py` defines its own `console` handler for the `rag_chat`/`core`/`django` loggers, unfiltered by `DEBUG`. This is deliberate: Django's *default* logging config only sends `django.request` (unhandled-exception tracebacks, including for 500s) to console when `DEBUG=True`, via a `require_debug_true` filter — so with `DEBUG` correctly `False` in production, server errors would otherwise be invisible in Render's logs too, not just absent from the HTTP response. Don't remove the `django` logger entry from this config without replacing it some other way, or 500s in production go dark again.
