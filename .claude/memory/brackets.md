---
feature: brackets
status: stable
last_updated: 2026-08-30
backend_paths:
  - backend/brackets/
frontend_paths:
  - frontend/src/pages/bracketpage.jsx
  - frontend/src/components/brackets/
related_docs:
  - docs/ARCHITECTURE.md#concurrency-rules (lock ordering, quoted in full)
  - docs/ARCHITECTURE.md#bracket-generation-backendbracketsservicespy
  - docs/EDGE_CASES.md (Bracket engine section)
---

# Brackets (generation, progression, lock ordering)

## What it does

Bracket generation and progression for all supported formats, decoupled from `tourny_regist` via a plain `tournament` FK. `Match` nodes link forward via `next_match`/`next_match_slot` (winner path) and `loser_next_match`/`loser_next_match_slot` (loser path, double-elim).

## How it works

**`services.py` (~1500 lines) is the important file** — this is one of only two apps with a real service layer (the other is `tourny_regist`), because bracket generation is a graph-construction problem with real invariants (no fabricated players, no one-loss elimination in double-elim bugs, deterministic seeding).

All formats pull players from `tournament.registrations.filter(checked_in=True)`, ordered by registration time — that order *is* the seeding rank. Each `generate_*_bracket(tournament)` is a pure builder creating `Bracket`+`Match` rows:

- **Single elimination** — pads to next power of two (`_seed_order`/`_seed_slots`, byes land on top seeds), auto-completes round-1 byes immediately via `complete_match`.
- **Double elimination / 3-game guarantee** — share `_build_double_elim_core`: winners bracket, then `_pair_losers`/`_drop_in` thread losers into the losers bracket. 3-game guarantee adds one bonus match (`Match.Side.GUARANTEE`) for round-1 double-losers. Both require an exact power of two (double-elim ≥4, guarantee3 ≥8) — enforced via `ValidationError`, not silently rounded. `_build_losers_bracket` builds the losers bracket from the *actual* winners-bracket topology round by round, not the classic fixed seed-round/drop-in formula — this is why non-power-of-two fields still work correctly for these formats too, not just single elim.
- **Round robin** — standard circle-method (`_round_robin_rounds`).
- **Swiss** — round 1 by registration order; later rounds by `standings()`, avoiding rematches where possible (`_have_played`), falling back to one if pairing gets stuck. Generated one round at a time; `generate_next_swiss_round` refuses to advance until every match in the current round is `COMPLETED`.
- **Group stage + playoff** — two explicit phases: `generate_group_playoff_bracket` (split into round-robin groups) then `generate_group_playoff_bracket_phase2` (called separately once group play finishes; top standing per group feeds `_build_single_elim`).

`complete_match(match, winner, score)` is the single place that advances winners/losers into whatever `next_match`/`loser_next_match` pointers reference. **Any new bracket format must still terminate in matches wired through these same pointers.** `standings(tournament, players=None)` ranks by completed-match win count, ties broken by registration order.

## The lock-ordering rule (load-bearing — read before touching `select_for_update()` here)

**Total lock order: Tournament, then Bracket, then Match.** Enforced by more than convention: `LockOrderAuditTests` (`brackets/tests.py`) statically parses `services.py`'s AST and fails the suite if a new `select_for_update()` appears that isn't accounted for in this ordering.

Why it exists: match completion naturally wants to lock the match then the tournament (M→T); bracket generation naturally locks the tournament then completes newly-created bye matches (T→M) — an inversion. `complete_match` takes the tournament lock *first* to resolve it, and every entry point follows suit. `_lock_tournament` is the only way this module takes a tournament lock — **adding a new multi-lock path starts from it, never a second parallel locking scheme.**

If you only need to lock a single `Tournament` row alone (not coordinating with a `Bracket`/`Match` lock), a local `select_for_update()` in `tourny_regist/views.py` is fine and doesn't need to interact with this ordering — three such isolated single-row locks already exist there (team join by invite code, registration-capacity check, admin-review double-decide guard).

## Invariants & gotchas

- `_is_bye_match` checks whether a slot is fed by an upstream match (`_fed_slots`), not just whether it's currently empty — a naive `bool(player1_id) != bool(player2_id)` would misclassify a round-2 match waiting on an unplayed feeder as a bye. Matters for 3-game-guarantee accounting.
- `_advance_into` refuses to displace a different player already standing in a slot — fails loudly (`ValidationError`) rather than silently corrupting the bracket graph. Re-writing the *same* player into a slot is allowed (safe retry).
- `override_match_result` rejects overriding a bye's result; `forfeit_match` rejects forfeiting against a bye — both are real reachable inputs (admin fat-fingering), not defensive dead code.
- Result submissions for one tournament serialize on its row (a documented, accepted cost of the lock order) — low-frequency, short transactions, so this is fine.
- Concurrent bracket generation is already handled correctly: `_require_no_existing_bracket` (services.py) takes the tournament lock *before* checking `Bracket.objects.filter(...).exists()`, inside every generator's `@transaction.atomic` — two simultaneous `POST /brackets/` requests serialize, and the loser gets a clean `ValidationError` (400), never an `IntegrityError`/500. Verified directly by `brackets/tests.py:ConcurrentGenerationTests.test_simultaneous_bracket_generation_creates_exactly_one` (real threads). Don't rebuild this — it's already correct.
- `TournamentBracketView.get`/`TournamentMatchesView`/`MatchDetailView` are gated by `brackets/permissions.py:IsPublicOrTournamentStakeholder` (staff, the organizer, or a registered player/team member pass unconditionally; anyone else only once the tournament is `APPROVED` + published) — not a bare `IsAuthenticated`. `TournamentBracketView.post` (generation) still uses `IsTournamentStaffOrAdmin` via `get_permissions()`'s method-based split; don't collapse the two back into one `permission_classes` list without preserving that split. See docs/SECURITY.md's IDOR-audit section for why this changed.
- `generate_group_playoff_bracket`'s `num_groups` param is validated (`try/except (TypeError, ValueError)` → `ValidationError`) before use — a malformed value from the request no longer reaches a bare `int()` call that would 500.

## Known edge cases

`docs/EDGE_CASES.md`'s "Bracket engine" section covers non-power-of-two fields, round-1 byes, bye-vs-unfilled-slot disambiguation, simultaneous result submissions, and Swiss lone-survivor pairing — read before modifying any generation/progression function.

## Change log

- 2026-08-30 — Production-hardening pass: added `brackets/permissions.py:IsPublicOrTournamentStakeholder` and wired it into `TournamentBracketView.get`/`TournamentMatchesView`/`MatchDetailView` (previously no object-level check ran at all on these — any authenticated user could view any tournament's bracket regardless of publish status). Also fixed `generate_group_playoff_bracket`'s unvalidated `num_groups` (malformed input → 500 before, → 400 now). The concurrent-bracket-generation race was investigated and found already correctly handled (see Invariants above) — no code change there, just confirmed via the existing `ConcurrentGenerationTests`.
- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/ARCHITECTURE.md`/`EDGE_CASES.md`. No code changes made.
