# Feature memory index

One file per feature under `.claude/memory/`. Each entry: what it covers, and the backend/frontend paths it owns. See root [`CLAUDE.md`](../../CLAUDE.md) for the convention that governs how these get read and updated.

- [auth.md](auth.md) — registration/OTP email verification, login, Google OAuth, JWT/sessions, password reset, admin user management. `backend/core/`.
- [organizer.md](organizer.md) — organizer application, CNIC/company compliance docs, admin approval workflow. `backend/organizer/`.
- [games.md](games.md) — game catalog (Valorant, Tekken 8, CS2, PUBG Mobile, EA FC, ...) that tournaments and rulebooks key off of. `backend/games/`.
- [tournaments.md](tournaments.md) — Tournament/Team/Registration/Announcement, lifecycle state machine, admin-review escalation. `backend/tourny_regist/`.
- [brackets.md](brackets.md) — bracket generation/progression engine (all formats), lock ordering. `backend/brackets/`.
- [admin-review-disputes.md](admin-review-disputes.md) — cross-app admin-review escalation pattern, disputes, audit log. Spans `core`, `tourny_regist`, `brackets`.
- [rag-chat.md](rag-chat.md) — AI rulebook assistant: upload → chunk → embed → retrieve → rerank → generate. `backend/rag_chat/`.
- [partners.md](partners.md) — sponsor/partner listings. `backend/partners/`.
- [dashboard.md](dashboard.md) — read-only aggregate stats. `backend/dashboard/`.
- [frontend-infra.md](frontend-infra.md) — API client, auth context, route guards, layout, shadcn/ui setup — cross-cutting frontend plumbing not owned by one backend app.
- [deployment-ops.md](deployment-ops.md) — CI/CD, Docker boot sequence, Render/Vercel gotchas, environment config, health checks, past incidents.

## Feature → path quick lookup

| Path prefix | Feature file |
|---|---|
| `backend/core/` | [auth.md](auth.md) (also touches [admin-review-disputes.md](admin-review-disputes.md) for `Dispute`/`AdminReviewRequest`/`AuditLog`) |
| `backend/organizer/` | [organizer.md](organizer.md) |
| `backend/games/` | [games.md](games.md) |
| `backend/tourny_regist/` | [tournaments.md](tournaments.md) |
| `backend/brackets/` | [brackets.md](brackets.md) |
| `backend/rag_chat/` | [rag-chat.md](rag-chat.md) |
| `backend/partners/` | [partners.md](partners.md) |
| `backend/dashboard/` | [dashboard.md](dashboard.md) |
| `frontend/src/pages/auth.jsx`, `googlecallback.jsx`, `verifyemail.jsx`, `forgotpassword.jsx`, `resetpassword.jsx`, `accountsettings.jsx`, `adminusers.jsx` | [auth.md](auth.md) |
| `frontend/src/pages/organizer.jsx`, `adminorganizers.jsx` | [organizer.md](organizer.md) |
| `frontend/src/pages/games.jsx`, `gamedetail.jsx`, `admingames.jsx` | [games.md](games.md) |
| `frontend/src/pages/tournaments.jsx`, `tournamentdetail.jsx`, `createtournament.jsx`, `edittournament.jsx`, `mytournaments.jsx`, `createhub.jsx`, `admintournaments.jsx`, `components/tournaments/` | [tournaments.md](tournaments.md) |
| `frontend/src/pages/bracketpage.jsx`, `components/brackets/` | [brackets.md](brackets.md) |
| `frontend/src/pages/admindisputes.jsx`, `adminreviewrequests.jsx` | [admin-review-disputes.md](admin-review-disputes.md) |
| `frontend/src/pages/adminrulebooks.jsx`, `components/chatbot/` | [rag-chat.md](rag-chat.md) |
| `frontend/src/pages/adminpartners.jsx` | [partners.md](partners.md) |
| `frontend/src/pages/dashboard.jsx`, `adminoverview.jsx` | [dashboard.md](dashboard.md) |
| `frontend/src/lib/`, `frontend/src/components/ui/`, `Layout.jsx`, `App.jsx` | [frontend-infra.md](frontend-infra.md) |
| `.github/workflows/`, `backend/entrypoint.sh`, `backend/Dockerfile`, `docker-compose.yml`, `frontend/vercel.json`, `frontend/nginx.conf` | [deployment-ops.md](deployment-ops.md) |

Files that don't map cleanly to one feature (e.g. `config/settings.py`, which every feature reads from) belong to whichever feature the *specific setting being touched* affects — e.g. editing `DEFAULT_THROTTLE_RATES` for a new chat rate limit updates [rag-chat.md](rag-chat.md), not a generic "settings" file. If a change genuinely spans several features (e.g. a new cross-cutting security header), update every feature file it materially affects, or note it in [deployment-ops.md](deployment-ops.md) if it's operational rather than feature-specific.
