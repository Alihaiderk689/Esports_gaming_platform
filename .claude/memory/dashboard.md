---
feature: dashboard
status: stable
last_updated: 2026-08-28
backend_paths:
  - backend/dashboard/
frontend_paths:
  - frontend/src/pages/dashboard.jsx
  - frontend/src/pages/adminoverview.jsx
related_docs:
  - docs/ARCHITECTURE.md (Caching — none configured)
---

# Dashboard (aggregate stats)

## What it does

Read-only aggregate statistics (counts/summaries across tournaments, players, organizers, etc.) surfaced to players/organizers and admins.

## How it works

No `services.py` — read-only aggregation directly in `views.py`. No caching layer exists anywhere in this codebase (`docs/ARCHITECTURE.md#caching`), so every dashboard query hits Postgres directly on each request — worth knowing before assuming a stale-looking number is a caching bug rather than a query/logic one.

## Change log

- 2026-08-28 — Initial memory file seeded from `CLAUDE.md`. No code changes made.
