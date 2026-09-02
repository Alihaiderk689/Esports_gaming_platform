---
feature: tournaments
status: stable
last_updated: 2026-08-30
backend_paths:
  - backend/tourny_regist/
frontend_paths:
  - frontend/src/pages/tournaments.jsx
  - frontend/src/pages/tournamentdetail.jsx
  - frontend/src/lib/registrationStatus.js
  - frontend/src/pages/createtournament.jsx
  - frontend/src/pages/edittournament.jsx
  - frontend/src/pages/mytournaments.jsx
  - frontend/src/pages/createhub.jsx
  - frontend/src/pages/admintournaments.jsx
  - frontend/src/components/tournaments/
related_docs:
  - docs/ARCHITECTURE.md#authorization-architecture (admin-review escalation)
  - docs/EDGE_CASES.md (Tournament lifecycle, Registration & team concurrency sections)
  - docs/SECURITY.md#business-logic--state-machine-invariants
---

# Tournaments (Tournament, Team, Registration, Announcement)

## What it does

The core domain app: `Tournament` creation/approval/publishing, team formation, player registration and check-in, and announcements. Owned by an approved `Organizer` (organizer.md).

## How it works

**Service layer** (unusual for this codebase — most apps don't have one): `lifecycle.py` (submit/resubmit/cancel/reschedule/duplicate), `validation.py`, `emails.py`. Exists specifically so the organizer's self-service endpoint and the admin-approval path can call the *exact same* functions — see admin-review-disputes.md for why.

**Key models** (`models.py`):
- `Tournament` — owned by an `Organizer`; two independent axes: `status` (draft/pending/approved/rejected/cancelled) and `is_published` (visibility) — a tournament can be admin-approved but still hidden until the organizer publishes it. `game`/`team_size`/`bracket_format` are frozen once any registration, team, or bracket exists (`TournamentUpdateSerializer`) — resending the same value is fine, only an actual change is blocked.
- `Registration` — one per player per tournament (`UniqueConstraint`); `checked_in` gates bracket eligibility; `seed` (nullable) is a manual override consumed by `brackets.services.seed_players` ahead of registration-order fallback.
- `Team`/`TeamMembership` — team-based tournaments, joined via `invite_code`; `is_locked` freezes self-service join/leave once competitive activity starts (staff-only unlock/substitute after that).
- `Announcement` — organizer-posted, visible per `IsPublicOrOwner`.

**Lifecycle actions and the admin-review escalation pattern**: cancelling a tournament/registration or resetting a bracket checks "is this safe?" (no registrations yet / no bracket yet); if unsafe, raises `NeedsAdminReview` instead of executing — the view catches it, creates an `AdminReviewRequest`, returns `202`. See admin-review-disputes.md for the full pattern (also used by `brackets`). The safety check lives *inside* `lifecycle.py`'s functions, not the view, so a future third caller gets the same protection automatically (`tourny_regist/tests.py:ServiceLayerInvariantTests` proves this by calling the function directly with no view in between).

**Rescheduling** updates `starts_at`/`ends_at`/`registration_deadline` in place and logs old values to `AuditLog.metadata` — no separate `POSTPONED` status. **Duplicating** copies only configuration (game, format, venue, contacts), never participants/brackets/documents — new tournament starts `DRAFT`.

## Invariants & gotchas

- **Concurrency**: `RegistrationCreateView`/`TeamRegisterView`/`TeamJoinView`/`TeamCreateView` all lock the `Tournament` row (`select_for_update()`) for their whole check-then-create sequence — this was a real, found-and-fixed race (overselling the last slot; a player joining two teams at once). Any new check-then-act flow on `Tournament`/`Team`/`Registration` state must follow this same pattern.
- **Bracket-frozen state**: once `hasattr(tournament, 'bracket')`, check-in status is frozen both directions and hard-deleting a registration is blocked entirely — withdrawal past that point must go through `disqualify_registration`/`cancel_registration`, which know how to unwind a live match (auto-forfeit). Don't add a new registration-mutating endpoint without checking this.
- **Terminal statuses**: `RegistrationReviewSerializer` treats `DISQUALIFIED`/`CANCELLED` as terminal (can't be reinstated via a plain `PATCH {"status": "approved"}`) — reviewing `APPROVED` ↔ `REJECTED` is still allowed (e.g. fraudulent payment proof discovered after approval).
- **Duplicate review requests**: `AdminReviewRequest.Meta` has a partial `UniqueConstraint` (one `pending` request per target+type) — a retried cancel click is a clean no-op (caught `IntegrityError`), not a queue of duplicates.
- Substituting a team member only swaps the roster (`TeamMembership`), never `Match.player1`/`player2` — can't retroactively rewrite who played a completed match.
- `brackets` is decoupled via a plain `tournament` FK, not a tight coupling — see brackets.md for where the boundary is and the lock-ordering rule that governs anything touching both apps.
- **Frontend check-in affordance is derived from one shared source of truth**: `frontend/src/lib/registrationStatus.js:canCheckIn(registration, hasFee)` — both `RegistrationRow` and `RegistrationDetailDialog` in `tournamentdetail.jsx` call it (or share its `TERMINAL_NEGATIVE_STATUSES` list). They previously implemented this independently and drifted: the dialog only excluded `rejected`, so a `cancelled`/`disqualified` registration still showed an active "Check in" button there (though not in the table row). The backend (`RegistrationCheckInView`) was always correctly authoritative regardless — this was purely a frontend affordance bug. Don't reintroduce a second inline copy of this logic.
- `TournamentSeedingView`/`TeamSubstituteView` now validate that `registration_id`/`seed`/`outgoing_player_id`/`incoming_player_id` are actually numeric before using them (→ `ValidationError`/400) — previously a malformed value reached a bare `int()`/ORM pk coercion and 500'd.
- `AdminTournamentListView`/`AdminOrganizerListView` (organizer.md) now paginate (`core.pagination.StandardResultsPagination`, 20/page) — response shape is `{count, next, previous, results}`, not a bare array. `AdminUserListView` (auth.md/core) too, same pagination class. Public-facing list endpoints (`/api/tournaments/`, `/api/players/`, `/api/partners/`) were deliberately left unpaginated — staff-only admin lists are the more plausible "grows unbounded over time" case, and changing a public endpoint's response shape has more consumers to keep in sync for less benefit.

## Known edge cases

`docs/EDGE_CASES.md`'s "Tournament lifecycle" and "Registration & team concurrency" sections document several real, found-and-fixed gaps here (raising `team_size` after registration, hard-deleting a registration post-bracket, checking in after a bracket exists, reinstating a disqualified registration) — read before touching any registration/team/tournament state-mutating endpoint.

## Change log

- 2026-08-30 — Production-hardening pass: fixed the check-in-affordance drift between `RegistrationRow`/`RegistrationDetailDialog` (extracted `frontend/src/lib/registrationStatus.js`); added input validation to `TournamentSeedingView`/`TeamSubstituteView` (malformed ids/seeds now 400, not 500); added pagination to `AdminTournamentListView`.
- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/ARCHITECTURE.md`/`EDGE_CASES.md`/`SECURITY.md`. No code changes made.
