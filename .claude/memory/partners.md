---
feature: partners
status: stable
last_updated: 2026-08-28
backend_paths:
  - backend/partners/
frontend_paths:
  - frontend/src/pages/adminpartners.jsx
related_docs: []
---

# Partners (sponsor listings)

## What it does

Sponsor/partner listings shown on the platform. Simple CRUD-shaped app.

## How it works

No `services.py` — logic lives directly in `views.py`/`serializers.py`. `partners/permissions.py` follows the same staff-always-passes, owner-FK-otherwise pattern as `tourny_regist.permissions.IsTournamentStaffOrAdmin`.

## Change log

- 2026-08-28 — Initial memory file seeded from `CLAUDE.md`. No code changes made.
