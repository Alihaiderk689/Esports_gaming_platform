---
feature: frontend-infra
status: stable
last_updated: 2026-08-30
frontend_paths:
  - frontend/src/lib/api.js
  - frontend/src/lib/appauth.jsx
  - frontend/src/lib/*route.jsx
  - frontend/src/lib/routeAfterLogin.js
  - frontend/src/components/ui/
  - frontend/src/components/errorboundary.jsx
  - frontend/src/App.jsx
  - frontend/src/Layout.jsx
  - frontend/vite.config.js
  - frontend/jsconfig.json
  - frontend/eslint.config.js
  - frontend/src/test/setup.js
  - frontend/components.json
related_docs:
  - docs/ERROR_HANDLING.md#frontend-error-handling
---

# Frontend infrastructure (API client, auth context, routing, UI primitives)

## What it does

Cross-cutting frontend plumbing that every feature page depends on but that isn't owned by any single backend app: the fetch client, auth context, route guards, error boundary, and shadcn/ui component setup.

## How it works

- **`src/lib/api.js`** — single fetch-based client (`api.get/post/patch/put/delete`). The access token is an in-memory-only module variable (`tokenStorage`, never localStorage/sessionStorage — gone on every page reload by design); the refresh token lives entirely in an httpOnly cookie (`esp_refresh`, set/read server-side, `core/cookies.py`) that JS never touches. `refreshToken()` (exported) POSTs `/api/auth/token/refresh/` with `credentials: "include"` and is what `request()`/`requestBlob()` call on a 401 to retry once, and what `appauth.jsx` calls directly on mount for the silent-relogin-on-reload flow. A `withCredentials` request option (only set by `appauth.jsx`'s login/register/google-login/logout calls) controls whether a given `fetch()` sends/accepts the cookie — every other call stays credentials-free. `handleResponse` normalizes every non-2xx response into one `Error`: prefers `data.detail`, falls back to flattening a DRF field-error dict (`Object.values(msg).flat().join(" ")` — tolerates both the list-per-field shape and the bare-string shape a directly-raised `ValidationError` can produce), falls back to `Request failed (${status})` if the body isn't JSON at all (Django's bare HTML 500 page). Original body preserved on `err.data` for callers needing the structured shape (e.g. `VerifyEmailView`'s `attempts_remaining`, read as `data.attempts_remaining` directly, not `[0]` — see docs/ERROR_HANDLING.md for why response shape isn't uniform across endpoints). `safeFetch` catches `fetch()` itself throwing (network unreachable, CORS, DNS) separately from a real HTTP error response.
- **`src/lib/appauth.jsx`** — `AppAuthProvider`/`useAuth()`, wraps the whole app. `fetchMe()` attempts a silent `refreshToken()` (via the httpOnly cookie) whenever there's no in-memory access token before concluding the user is logged out — this runs on every mount/reload, not just when a token was never issued, since the in-memory token itself doesn't survive a reload. Exposes `login`/`register`/`googleLogin`/`logout`/`logoutAllSessions`/`refreshUser`.
- **Route guards** (`src/lib/*route.jsx`) — composed as nested `<Route>` wrappers in `App.jsx`, not per-page checks: `ProtectedRoute` (authenticated), `GuestRoute` (guest-only, e.g. `/login`), `AdminRoute` (staff only), `NotAdminRoute` (redirects staff away from the player-facing shell), `OrganizerOrAdminRoute` (gates `/players`, `/create`, `/my-tournaments`, `/tournaments/:id/edit`). Admin pages live under `AdminLayout` at `/admin/*`; player/organizer pages under `AppLayout`.
- **`src/pages/`** — one file per route, wired explicitly in `App.jsx` (no file-based routing).
- **`src/components/ui/`** — shadcn/ui primitives (style: "new-york", base color: neutral, icons: lucide). Regenerate/add via the shadcn CLI (`components.json`) rather than hand-rolling new primitives.
- **`src/components/errorboundary.jsx`** — class-based (required for `componentDidCatch`), wraps the whole app in `main.jsx`. Catches render-time JS errors only (not API errors, which never throw inside React's render cycle) — shows a reload/home fallback instead of an unhandled error unmounting to a blank screen. Logs to `console.error` only, no Sentry integration on the frontend.
- Path alias `@/*` → `src/*` (both `vite.config.js` and `jsconfig.json`).
- `jsconfig.json`'s `exclude` (`src/components/ui`, `src/api`) only keeps those out as *root* files for `npm run typecheck` — `tsc` still checks their contents whenever an included file imports them (most do), so typecheck errors can and do surface inside "excluded" paths too. `src/lib` was removed from `exclude` (it's now linted, see below) but `**/*.test.js`/`**/*.test.jsx` were added — vitest/jest-dom test-only globals (`vi.fn()`, `.toBeInTheDocument()`, etc.) aren't typed under this project's `"types": []` config, so a co-located test file would otherwise fail `npm run typecheck` for reasons unrelated to real type errors.
- **Vitest is the frontend test runner** (`vite.config.js`'s `test` block, `src/test/setup.js` loads `@testing-library/jest-dom`) — `npm run test` / `npm run test:watch`. Tests are co-located (`*.test.js`/`*.test.jsx` next to the file they cover): `src/lib/api.test.js`, `src/lib/appauth.test.jsx`, `src/lib/registrationStatus.test.js`, `src/pages/verifyemail.test.jsx`. Coverage is deliberately targeted (auth token flow, API error handling, OTP-resend error surfacing, check-in eligibility), not exhaustive — most pages have no tests.
- `eslint.config.js` now lints `src/lib/**` (previously excluded entirely) and has `react-hooks/exhaustive-deps` enabled at `"warn"` (not `"error"` — plenty of pre-existing components have never been checked against it; `npm run lint`'s `--quiet` flag means a warning doesn't fail the command either way). Spreading `eslint-plugin-react-hooks`'s own `configs['recommended-latest']` doesn't actually work in this config's structure — the file's own explicit `rules: {...}` object literal is written *after* the `...pluginJs.configs.recommended`/`...pluginReact.configs.flat.recommended` spreads, so in plain JS object-literal semantics it completely replaces whatever `rules` object those spreads contributed rather than merging with it (this was already true before touching `react-hooks`; the two `.configs.recommended` spreads' own `rules` were already dead for the same reason — a pre-existing quirk of this file, not something this pass introduced or attempted to fix). New rules must be added directly into that literal `rules: {}` block to actually take effect.
- App-level route components (`src/App.jsx`) are `React.lazy()`-loaded with one `<Suspense>` boundary around the whole `<Routes>` tree — route *guard* components and layouts stay eagerly imported. Turned a single ~989KB build chunk into a shared ~509KB chunk plus a small per-route chunk each.
- `CORS_ALLOW_CREDENTIALS = True` on the backend (changed from `False` — see auth.md's change log) — only `api.js` calls that pass `{ withCredentials: true }` (login/register/google-login/logout/refresh) send `credentials: "include"`; every other `fetch()` call must stay credentials-free, since there's nothing else legitimate for a cross-site cookie to unlock and widening it further isn't free (see `docs/SECURITY.md#jwt`'s accepted-residual-risk note).

## Change log

- 2026-08-30 — Production-hardening pass: added Vitest + React Testing Library (previously no test runner existed at all); enabled `react-hooks/exhaustive-deps` and extended ESLint to cover `src/lib`; added route-level code splitting (`React.lazy`/`Suspense`) in `App.jsx`; `api.js`/`appauth.jsx` rewritten for the in-memory-access-token/httpOnly-refresh-cookie migration (see auth.md's change log for the detailed why). `jsconfig.json` exclude list updated accordingly.
- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/ERROR_HANDLING.md`. No code changes made.
