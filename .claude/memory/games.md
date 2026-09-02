---
feature: games
status: stable
last_updated: 2026-08-28
backend_paths:
  - backend/games/
frontend_paths:
  - frontend/src/pages/games.jsx
  - frontend/src/pages/gamedetail.jsx
  - frontend/src/pages/admingames.jsx
related_docs:
  - docs/ARCHITECTURE.md (Database design)
---

# Games (catalog)

## What it does

The platform's game catalog — Valorant, Tekken 8, Counter-Strike 2, PUBG Mobile, EA Sports FC, and others — that `tourny_regist.Tournament` and `rag_chat` rulebooks both key off of by name/slug.

## How it works

No `services.py` — mostly read-only/CRUD, gated by `games/permissions.py` for the object-level checks (staff always passes, same pattern as `tourny_regist.permissions.IsTournamentStaffOrAdmin`).

Note: `rag_chat`'s `game_detector.py` matches against both this catalog *and* a hardcoded list of common esports titles (`_COMMON_ESPORTS_GAMES`) — the RAG assistant's scope is "esports rules in general," not strictly limited to games this platform currently hosts tournaments for. See rag-chat.md.

## Invariants & gotchas

- Deleting or renaming a game here has downstream effects on `tourny_regist.Tournament` (keyed by game) and on `rag_chat` rulebook chunk tagging (keyed by detected/matched game name) — check both before a destructive catalog change.

## Change log

- 2026-08-28 — Initial memory file seeded from `CLAUDE.md`. No code changes made.
