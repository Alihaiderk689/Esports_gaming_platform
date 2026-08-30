import heapq
import math

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from brackets.models import Bracket, Match
from tourny_regist.models import Tournament

#: How many real games the 3-game-guarantee format promises every entrant.
GUARANTEED_GAMES = 3

# ---------------------------------------------------------------------------
# LOCK ORDER — Tournament, then Bracket, then Match.
#
# Every transaction in this module that takes more than one row lock takes them in
# that order, which makes deadlock impossible by construction rather than by argument:
# a cycle requires two transactions to acquire the same pair in opposite orders, and a
# single global ordering forbids that.
#
# The rule exists because the obvious implementation violates it. Match completion
# naturally wants to lock the match and then, once a result decides the event, the
# tournament (M -> T); bracket generation naturally locks the tournament and then
# completes newly-created bye matches (T -> M). Those two are an inversion. It happens
# not to deadlock today, because the matches generation locks are rows it created in
# its own uncommitted transaction and no other transaction can see or lock them — but
# that reasoning rests on row visibility and would quietly stop holding the moment a
# generator locked a pre-existing match. So `complete_match` takes the tournament lock
# first instead, and every entry point below follows suit.
#
# Re-locking a row already held by the same transaction is a no-op in PostgreSQL, so
# the redundant tournament lock in `finalize_tournament_champion` costs nothing when
# reached through match completion.
#
# The practical cost is that result submissions for one tournament serialize on its
# row. That is acceptable here — results for a single tournament are low-frequency and
# each transaction is short — and it is what buys a provable ordering.
#
# `_lock_tournament` is the only way this module takes a tournament lock; adding a new
# multi-lock path means starting from it. `tests.LockOrderAuditTests` fails if a
# `select_for_update()` appears anywhere in the engine that this rule has not accounted
# for.
# ---------------------------------------------------------------------------


def _lock_tournament(tournament_id):
    """Acquire the outermost lock. See the LOCK ORDER note above."""
    return Tournament.objects.select_for_update().get(pk=tournament_id)


def _lock_bracket(bracket_id):
    """Acquire the mid-level lock. The caller must already hold the tournament lock."""
    return Bracket.objects.select_for_update().get(pk=bracket_id)


def eligible_participants(tournament):
    """Who is *allowed* into a bracket: checked-in registrations only. No-shows who
    registered but never checked in are excluded. This answers eligibility only — it
    says nothing abouta how strong anyone is."""
    return list(tournament.registrations.filter(checked_in=True).select_related('player'))


def seed_players(tournament):
    """The ordered seed list every bracket builder consumes: index 0 is seed 1.

    Eligibility and seeding are deliberately separate questions. Registrations with a
    manually-assigned Registration.seed (see tourny_regist.views.TournamentSeedingView)
    sort by that number, ranked above every unseeded registration; unseeded
    registrations fall back to registration-time order, exactly as before manual
    seeding existed. The (0, ...)/(1, ...) tuple prefix is what makes this safe to
    compare — every seeded registration's key sorts before every unseeded one
    regardless of the differing second-element types, since Python tuple comparison
    never inspects the second element unless the first is equal."""
    registrations = eligible_participants(tournament)
    registrations.sort(key=lambda r: (0, r.seed) if r.seed is not None else (1, r.registered_at, r.pk))
    return [r.player for r in registrations]


def _checked_in_players(tournament):
    """Backwards-compatible alias — see `seed_players`."""
    return seed_players(tournament)


def _player_summary(player):
    if player is None:
        return None
    name = f'{player.first_name} {player.last_name}'.strip()
    return {'id': player.pk, 'email': player.email, 'name': name or player.email}


def preview_bracket(tournament, bracket_format):
    """Read-only dry run of what generate_*_bracket(tournament) would build for
    `bracket_format` — no DB writes, no Bracket/Match rows created. Lets the
    organizer review seeding, round-1 matchups, and byes before committing
    (spec: "Generate -> Preview -> Organizer confirmation -> Activate").
    Deliberately reuses seed_players/_seed_slots/_round_robin_rounds rather
    than a parallel implementation, so what's previewed can't drift out of
    sync with what the real generator actually builds."""
    players = seed_players(tournament)
    n = len(players)

    if bracket_format in (Bracket.Format.SINGLE, Bracket.Format.DOUBLE, Bracket.Format.GUARANTEE3):
        minimum = {Bracket.Format.SINGLE: 2, Bracket.Format.DOUBLE: 4, Bracket.Format.GUARANTEE3: 8}[bracket_format]
        if n < minimum:
            return {'player_count': n, 'error': f'Needs at least {minimum} checked-in players — you have {n}.'}
        bracket_size, slots = _seed_slots(players)
        round1 = [
            {
                'player1': _player_summary(slots[2 * i]), 'player2': _player_summary(slots[2 * i + 1]),
                'is_bye': bool(slots[2 * i]) != bool(slots[2 * i + 1]),
            }
            for i in range(bracket_size // 2)
        ]
        return {
            'player_count': n, 'bracket_size': bracket_size,
            'total_rounds': bracket_size.bit_length() - 1, 'round1': round1,
        }

    if bracket_format == Bracket.Format.ROUND_ROBIN:
        if n < 2:
            return {'player_count': n, 'error': f'Needs at least 2 checked-in players — you have {n}.'}
        rounds = _round_robin_rounds(players)
        round1 = [
            {'player1': _player_summary(p1), 'player2': _player_summary(p2), 'is_bye': False}
            for p1, p2 in (rounds[0] if rounds else [])
        ]
        return {'player_count': n, 'total_rounds': len(rounds), 'round1': round1}

    if bracket_format == Bracket.Format.SWISS:
        if n < 2:
            return {'player_count': n, 'error': f'Needs at least 2 checked-in players — you have {n}.'}
        return {'player_count': n, 'total_rounds': swiss_round_count(n)}

    if bracket_format == Bracket.Format.GROUP_PLAYOFF:
        num_groups = max(2, round(n / 4)) if n else 2
        if n < 2 * num_groups:
            return {'player_count': n, 'error': f'Needs at least {2 * num_groups} checked-in players for {num_groups} groups — you have {n}.'}
        return {'player_count': n, 'num_groups': num_groups}

    raise ValidationError({'format': f'Unknown bracket format "{bracket_format}".'})


def _require_no_existing_bracket(tournament):
    """Take an exclusive lock on the tournament, then refuse if it already has a
    bracket.

    The lock is the point. `Bracket.tournament` is a OneToOneField, so the database
    already refuses a second bracket — but an unlocked existence check does not
    serialize: two concurrent requests can both see no bracket, both proceed, and the
    loser gets an IntegrityError surfaced as a 500 rather than the intended validation
    error. Locking the tournament row inside the generator's transaction makes the
    second request wait, then see the bracket the first one committed.

    It matters beyond tidiness: most queries in this module are tournament-wide
    (`_played_pairs`, `standings`), so a second bracket's matches would be folded into
    the first's standings and pairings if that unique constraint ever went away."""
    _lock_tournament(tournament.pk)
    if Bracket.objects.filter(tournament_id=tournament.pk).exists():
        raise ValidationError({'detail': 'This tournament already has a bracket.'})


def _require_minimum_players(players, minimum, format_label):
    if len(players) < minimum:
        raise ValidationError({
            'detail': f'{format_label} needs at least {minimum} checked-in players — you have {len(players)}.',
        })


def _next_power_of_two(n):
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def _seed_order(size):
    """Standard single-elimination seeding order for a bracket of `size` (a power of
    two): the seed numbers (1-indexed, 1 = top seed) in bracket-slot order — e.g.
    size=8 -> [1, 8, 4, 5, 2, 7, 3, 6] (round-1 pairs: 1v8, 4v5, 2v7, 3v6). Seed 1
    always lands in the same slot-pair as the highest (weakest/most likely absent)
    seed number, which is exactly why padding the field out with byes at the bottom
    of the seed list naturally gives byes to the top seeds first."""
    positions = [1]
    while len(positions) < size:
        mirror = len(positions) * 2 + 1
        positions = [value for p in positions for value in (p, mirror - p)]
    return positions


def _seed_slots(players):
    """Pad `players` (ranked best-first, i.e. registration order) out to the next
    power of two using standard bracket seeding, so byes land on the top seeds'
    first-round opponents rather than being clustered together. Returns
    (bracket_size, slots) where slots[i] is the player in bracket position i, or
    None for a bye."""
    bracket_size = _next_power_of_two(len(players))
    order = _seed_order(bracket_size)
    return bracket_size, [players[seed - 1] if seed <= len(players) else None for seed in order]


def _advance_into(target_id, slot, player_id):
    """Put `player_id` into `slot` of match `target_id`, locking that row first, and
    flip it to READY once both slots are occupied.

    Refuses to displace a different player already standing in that slot. The lock
    above prevents two concurrent writers racing for the slot, but it says nothing
    about a malformed graph routing two different sources into the same destination —
    that would quietly evict someone from a match they had earned, and the bracket
    would still look plausible afterwards. Failing loudly turns a silent corruption
    into something traceable. Re-writing the same player is allowed so a retry is
    harmless."""
    if target_id is None or player_id is None:
        return

    target = Match.objects.select_for_update().get(pk=target_id)
    field = 'player1' if slot == 1 else 'player2'

    occupant_id = getattr(target, f'{field}_id')
    if occupant_id is not None and occupant_id != player_id:
        raise ValidationError({
            'detail': 'Bracket routing attempted to overwrite an occupied match slot.',
        })

    setattr(target, f'{field}_id', player_id)

    updated = [field]
    if target.player1_id and target.player2_id and target.status != Match.Status.COMPLETED:
        target.status = Match.Status.READY
        updated.append('status')
    target.save(update_fields=updated)


def _retract_from(target_id, slot, player_id):
    """Inverse of `_advance_into` — used only by `override_match_result`, and only once
    it has confirmed `target_id` has no recorded result yet. Clears `player_id` back
    out of `slot`, downgrading the target to PENDING if it had reached READY.

    Does nothing if the slot no longer holds `player_id` (defensive — should not
    happen given the caller's own locking, but a silent no-op is the right failure
    mode for "someone else already moved on" rather than corrupting an unrelated
    occupant)."""
    if target_id is None or player_id is None:
        return

    target = Match.objects.select_for_update().get(pk=target_id)
    field = 'player1' if slot == 1 else 'player2'
    if getattr(target, f'{field}_id') != player_id:
        return

    setattr(target, f'{field}_id', None)
    updated = [field]
    if target.status == Match.Status.READY:
        target.status = Match.Status.PENDING
        updated.append('status')
    target.save(update_fields=updated)


@transaction.atomic
def complete_match(match, winner, score=''):
    """Record `winner` and push them (and the loser, where the graph routes one) into
    the next match.

    The match row is re-read under `select_for_update()` rather than trusting the
    instance handed in. Atomicity alone does not make this safe: two requests reporting
    the same match can both read it as READY, both pass the already-completed check,
    and both write — the second silently overwriting the first's winner and, worse,
    propagating a second player into the next match's slots. Taking a row lock forces
    the second request to wait and then fail the completed check, which is the point at
    which "this match already has a result" becomes true. Downstream matches are locked
    as they are written for the same reason.

    Validates that the winner actually played in this match. Without that check a
    caller passing an unrelated user would silently record them as the winner *and*
    mis-derive the loser as player1, corrupting both onward paths.

    A one-sided match is a bye, and this is the function that advances it during
    generation, so it is accepted here — but only with its sole occupant as the winner,
    since `player2_id` is NULL and the participant check admits nothing else. No loser
    is derived, so a bye never routes anyone onward. Reporting a *result* against a bye
    is rejected at the API boundary (`MatchResultView`), which is where the distinction
    between "advance this bye" and "record a game that was played" belongs.

    The instance passed in is updated to match what was written, so callers holding it
    (the API serializes the same object) see the completed state."""
    # Tournament before match — see the LOCK ORDER note at the top of this module. The
    # result of this match may decide the tournament, and finalisation locks the
    # tournament row; taking it here rather than there is what keeps every path in this
    # module on a single global ordering.
    _lock_tournament(match.tournament_id)
    locked = Match.objects.select_for_update().get(pk=match.pk)

    winner_id = winner.pk if winner is not None else None
    if winner_id is None or winner_id not in (locked.player1_id, locked.player2_id):
        raise ValidationError({'winner': 'The winner must be one of the players in this match.'})
    if locked.status == Match.Status.COMPLETED:
        raise ValidationError({'detail': 'This match has already been completed.'})

    loser_id = locked.player2_id if locked.player1_id == winner_id else locked.player1_id

    locked.winner_id = winner_id
    locked.score = score
    locked.status = Match.Status.COMPLETED
    locked.save(update_fields=['winner', 'score', 'status'])

    _advance_into(locked.next_match_id, locked.next_match_slot, winner_id)
    _advance_into(locked.loser_next_match_id, locked.loser_next_match_slot, loser_id)

    _open_grand_final_reset_if_needed(locked, winner_id)

    match.winner_id = winner_id
    match.score = score
    match.status = Match.Status.COMPLETED
    return locked


def _open_grand_final_reset_if_needed(match, winner_id):
    """Standard double elimination: the winners-bracket finalist arrives at the grand
    final unbeaten, the losers-bracket finalist arrives with one loss. So a single
    grand final can only settle the title if the WB finalist wins it.

    If the LB finalist wins, both players now hold exactly one loss and the title is
    undecided — a second "reset"/decider match must be played. That is created here,
    on demand, rather than up front: an unconditional reset match would be a match
    that frequently cannot happen, which is exactly the kind of phantom node the rest
    of this module avoids. (Bracket UIs commonly show the reset as a conditional
    node; representing it as "created only once it is real" is our own choice, and
    keeps `next_match`-based champion detection honest.)

    Slot 1 of the first grand final is always the WB finalist — see
    `_attach_grand_final` — which is what makes "did the LB finalist win?" a plain
    slot comparison rather than a bracket-walk."""
    if match.bracket_side != Match.Side.GRAND_FINAL or match.round_number != 1:
        return None
    if winner_id != match.player2_id:
        return None  # WB finalist won outright: no reset, tournament over
    existing = Match.objects.filter(
        bracket_id=match.bracket_id, bracket_side=Match.Side.GRAND_FINAL, round_number=2,
    ).first()
    if existing is not None:
        return existing
    return Match.objects.create(
        bracket_id=match.bracket_id, tournament_id=match.tournament_id,
        bracket_side=Match.Side.GRAND_FINAL, round_number=2, position=0,
        player1_id=match.player1_id, player2_id=match.player2_id, status=Match.Status.READY,
    )


def _completed_matches(tournament, sides=None):
    """Completed matches for `tournament`, optionally restricted to certain
    `bracket_side` values so one stage's results can't leak into another's table."""
    queryset = Match.objects.filter(tournament=tournament, status=Match.Status.COMPLETED)
    if sides:
        queryset = queryset.filter(bracket_side__in=list(sides))
    return queryset


def _real_opponents(tournament, player_ids, sides=None):
    """{player_id: [opponent_id, ...]} over completed matches with two real players.
    Byes are excluded on purpose: a bye is not an opponent, and counting it as one
    would corrupt every opponent-strength tiebreak below."""
    opponents = {pid: [] for pid in player_ids}
    rows = _completed_matches(tournament, sides).filter(
        player2__isnull=False,
    ).order_by('round_number', 'position').values_list('player1_id', 'player2_id')
    for p1, p2 in rows:
        if p1 in opponents and p2 is not None:
            opponents[p1].append(p2)
        if p2 in opponents and p1 is not None:
            opponents[p2].append(p1)
    return opponents


def _buchholz(player_id, context):
    """Sum of the scores of everyone this player actually faced."""
    return sum(context['scores'].get(o, 0) for o in context['opponents'].get(player_id, []))


def _median_buchholz(player_id, context):
    """Buchholz with the single strongest and single weakest opponent discarded, which
    blunts the distortion of having drawn one runaway leader or one player who lost
    everything. The trim only applies with enough opponents to leave something behind
    (3+); below that it degrades to plain Buchholz, which is the conventional
    treatment for a short pairing history."""
    opponent_scores = sorted(context['scores'].get(o, 0) for o in context['opponents'].get(player_id, []))
    if len(opponent_scores) >= 3:
        opponent_scores = opponent_scores[1:-1]
    return sum(opponent_scores)


def _head_to_head(player_id, context):
    """Wins against the players this one is actually tied with.

    Restricted to opponents on the same score, which is what "head to head" means as a
    tiebreak: it settles a tie by how the tied players fared against each other, and
    says nothing about anyone else. Counting wins over *all* opponents would just
    restate the score and break no ties at all. In a three-way tie this correctly
    ranks by the mini-league between those three."""
    score = context['scores'].get(player_id, 0)
    return sum(
        1 for opponent_id, won in context['results'].get(player_id, [])
        if won and context['scores'].get(opponent_id, 0) == score
    )


def _sonneborn_berger(player_id, context):
    """Sum of the scores of opponents this player beat — weights *who* you beat rather
    than merely who you met."""
    total = 0
    for opponent_id, won in context['results'].get(player_id, []):
        if won:
            total += context['scores'].get(opponent_id, 0)
    return total


#: Tiebreak registry. Each entry takes (player_id, context) and returns a number where
#: higher is better; `standings(..., tiebreakers=[...])` applies them in order. Adding
#: head-to-head, points differential, etc. means adding a function here — no caller of
#: `standings` and no other format has to change.
TIEBREAKERS = {
    'buchholz': _buchholz,
    'head_to_head': _head_to_head,
    'median_buchholz': _median_buchholz,
    'sonneborn_berger': _sonneborn_berger,
}

#: Default tiebreak chain per format.
#:
#: Swiss uses opponent-strength measures because players face wildly different
#: schedules; median-Buchholz leads because it is the more robust of the two.
#:
#: Round robin and group stages instead lead with head-to-head: everyone plays
#: everyone (within their group), so the mutual result between tied players exists and
#: is the fairest thing to rank on, with Sonneborn-Berger — which weights *who* you
#: beat — behind it. These formats are built to produce level records, so leaving them
#: to fall through to registration order would let a three-way tie be settled by who
#: signed up first.
#:
#: Elimination formats appear nowhere here on purpose: their standings come from the
#: bracket, not from a table.
FORMAT_TIEBREAKERS = {
    Bracket.Format.SWISS: ('median_buchholz', 'buchholz'),
    Bracket.Format.ROUND_ROBIN: ('head_to_head', 'sonneborn_berger'),
    Bracket.Format.GROUP_PLAYOFF: ('head_to_head', 'sonneborn_berger'),
}


def standings(tournament, players=None, tiebreakers=None, sides=None):
    """Rank `players` (defaults to every checked-in player) by completed-match win
    count, applying the named `tiebreakers` in order and falling back to registration
    order — see the `TIEBREAKERS` registry.

    `sides` restricts which `bracket_side` values count. Multi-stage formats need this:
    without it a group table would keep absorbing playoff results once the playoff
    starts, because every match belongs to the same tournament. Pass the stage you
    actually mean to report on.

    Returns [{'player', 'wins', 'played', 'losses', 'byes', 'tiebreaks'}, ...] where:
    - `played` counts real games only — a bye (player2 is NULL) is not a game against
      an opponent and never counts here, so two players on the same `played` really
      have faced the same number of opponents.
    - `wins` includes byes, because a bye advances the player exactly like a win and
      Swiss pairing ranks off this number (standard Swiss scores a bye as a full point).
      `wins - byes` is the number of wins actually earned against an opponent.
    - `losses` counts real games lost; a bye can never produce one.
    No schema change is needed for any of this — a bye is already distinguishable at
    the query level by `player2_id IS NULL`."""
    if players is None:
        players = _checked_in_players(tournament)

    wins = {p.pk: 0 for p in players}
    played = {p.pk: 0 for p in players}
    losses = {p.pk: 0 for p in players}
    byes = {p.pk: 0 for p in players}
    for m in _completed_matches(tournament, sides):
        is_bye = m.player2_id is None
        if is_bye:
            if m.player1_id in byes:
                byes[m.player1_id] += 1
        else:
            for pid in (m.player1_id, m.player2_id):
                if pid in played:
                    played[pid] += 1
                    if pid != m.winner_id:
                        losses[pid] += 1
        if m.winner_id in wins:
            wins[m.winner_id] += 1

    names = list(tiebreakers or ())
    unknown = [name for name in names if name not in TIEBREAKERS]
    if unknown:
        raise ValidationError({
            'detail': f'Unknown tiebreaker(s): {", ".join(sorted(unknown))}. '
                      f'Available: {", ".join(sorted(TIEBREAKERS))}.',
        })

    context = None
    if names:
        player_ids = [p.pk for p in players]
        results = {pid: [] for pid in player_ids}
        for m in _completed_matches(tournament, sides).filter(
            player2__isnull=False,
        ).order_by('round_number', 'position'):
            for pid, other in ((m.player1_id, m.player2_id), (m.player2_id, m.player1_id)):
                if pid in results:
                    results[pid].append((other, pid == m.winner_id))
        context = {
            'scores': wins,
            'opponents': _real_opponents(tournament, player_ids, sides),
            'results': results,
        }

    scores_by_name = {}
    for name in names:
        fn = TIEBREAKERS[name]
        scores_by_name[name] = {p.pk: fn(p.pk, context) for p in players}

    # Registration order is the final, always-deterministic fallback: two players who
    # are equal on every configured tiebreak must still rank in a stable order.
    order = {p.pk: i for i, p in enumerate(players)}
    ranked = sorted(
        players,
        key=lambda p: (-wins[p.pk], *(-scores_by_name[name][p.pk] for name in names), order[p.pk]),
    )
    return [
        {
            'player': p, 'wins': wins[p.pk], 'played': played[p.pk],
            'losses': losses[p.pk], 'byes': byes[p.pk],
            'tiebreaks': {name: scores_by_name[name][p.pk] for name in names},
        }
        for p in ranked
    ]


def format_standings(tournament, players=None):
    """Standings using the tiebreak chain appropriate to this tournament's format."""
    bracket = getattr(tournament, 'bracket', None)
    fmt = bracket.format if bracket else None
    return standings(tournament, players, tiebreakers=FORMAT_TIEBREAKERS.get(fmt))


def group_stage_standings(tournament, group_players):
    """The group table for `group_players`, counting group-stage matches only and
    applying the group tiebreak chain — which decides who qualifies, so falling back
    to registration order here would let sign-up time send a player through.

    Restricting by side is what keeps this correct once the playoff begins: those
    matches share the tournament, so an unrestricted query would fold playoff results
    back into the group table that decided who reached the playoff."""
    return standings(
        tournament, group_players,
        tiebreakers=FORMAT_TIEBREAKERS[Bracket.Format.GROUP_PLAYOFF],
        sides=(Match.Side.GROUP,),
    )


def _build_single_elim(bracket, tournament, players, bracket_side=Match.Side.WINNERS):
    """Build a full single-elimination tree for `players` (seeded and padded with byes
    to the next power of two — see `_seed_slots`), tagged with `bracket_side`. Byes are
    auto-completed once the tree is wired up, advancing that player with no action
    needed from anyone. Returns (final_match, total_rounds, rounds) where rounds[i] is
    the list of Match objects for round i+1 — reused by double elimination / 3-game
    guarantee to build their winners bracket without duplicating this seeding logic."""
    # Guarded here as well as in the generators because this is reusable internal
    # machinery: with fewer than two players there is no round 1 to build, and the
    # tree-walk below would index an empty list rather than say anything useful.
    _require_minimum_players(players, 2, 'An elimination bracket')
    bracket_size, slots = _seed_slots(players)
    total_rounds = bracket_size.bit_length() - 1

    round_matches = []
    for i in range(bracket_size // 2):
        p1, p2 = slots[2 * i], slots[2 * i + 1]
        initial_status = Match.Status.READY if (p1 and p2) else Match.Status.PENDING
        match = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=bracket_side,
            round_number=1, position=i, player1=p1, player2=p2, status=initial_status,
        )
        round_matches.append(match)

    rounds = [round_matches]
    current_round_matches = round_matches
    for round_number in range(2, total_rounds + 1):
        current_round_matches = _pair_winners(bracket, tournament, bracket_side, round_number, current_round_matches)
        rounds.append(current_round_matches)

    final_match = current_round_matches[0] if current_round_matches else round_matches[0]

    # Round-1 byes: with proper seeding (see _seed_slots) a pairing can never be two
    # byes facing each other, so exactly one of these branches applies per bye match.
    for match in round_matches:
        if match.player1_id and not match.player2_id:
            complete_match(match, match.player1, score='BYE')
        elif match.player2_id and not match.player1_id:
            complete_match(match, match.player2, score='BYE')

    return final_match, total_rounds, rounds


@transaction.atomic
def generate_bracket(tournament):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    _require_minimum_players(players, 2, 'Single elimination')
    total_rounds = _next_power_of_two(len(players)).bit_length() - 1
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=total_rounds)
    _build_single_elim(bracket, tournament, players)
    return bracket


def _pair_winners(bracket, tournament, side, round_number, sources):
    """Create one match per pair of `sources`, wiring each source's *winner* into it."""
    created = []
    for i in range(len(sources) // 2):
        m = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=side, round_number=round_number, position=i,
        )
        created.append(m)
        for slot, src in ((1, sources[2 * i]), (2, sources[2 * i + 1])):
            src.next_match = m
            src.next_match_slot = slot
            src.save(update_fields=['next_match', 'next_match_slot'])
    return created


def _pair_losers(bracket, tournament, round_number, sources, side=Match.Side.LOSERS):
    """Create one match per pair of `sources`, wiring each source's *loser* into it."""
    created = []
    for i in range(len(sources) // 2):
        m = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=side, round_number=round_number, position=i,
        )
        created.append(m)
        for slot, src in ((1, sources[2 * i]), (2, sources[2 * i + 1])):
            src.loser_next_match = m
            src.loser_next_match_slot = slot
            src.save(update_fields=['loser_next_match', 'loser_next_match_slot'])
    return created


def _wire_source(match, slot, source):
    """`source` is (src_match, role) where role is 'winner' or 'loser' — wire that
    match's *winner* (next_match/next_match_slot) or *loser*
    (loser_next_match/loser_next_match_slot) pointer at `match`/`slot`."""
    src_match, role = source
    if role == 'winner':
        src_match.next_match = match
        src_match.next_match_slot = slot
        src_match.save(update_fields=['next_match', 'next_match_slot'])
    else:
        src_match.loser_next_match = match
        src_match.loser_next_match_slot = slot
        src_match.save(update_fields=['loser_next_match', 'loser_next_match_slot'])


def _pair_sources(bracket, tournament, side, round_number, sources):
    """Pair up `sources` (a list of (match, role) tuples, each destined to produce one
    real player once its match is played) into real matches for one losers-bracket
    round. If `sources` has an odd count, the last one carries forward untouched into
    the pool for the next round instead of being forced into a fabricated match — this
    is how the losers bracket absorbs winners-bracket byes (and any other parity
    mismatch) without ever inventing a player or a match. (Which source "waits" is an
    arbitrary but deterministic choice: at bracket-construction time none of these
    sources have a known player yet — they're all pointers to still-unplayed matches —
    so there's no seed/fairness signal available to prefer one over another.)

    Returns (created, new_pool): the Match objects made this round, and this round's
    match winners (role 'winner') plus the carried-over source if any, ready to feed
    the next round."""
    carry = None
    if len(sources) % 2 == 1:
        carry = sources[-1]
        sources = sources[:-1]

    created = []
    for i in range(0, len(sources), 2):
        m = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=side, round_number=round_number, position=len(created),
        )
        created.append(m)
        _wire_source(m, 1, sources[i])
        _wire_source(m, 2, sources[i + 1])

    new_pool = [(m, 'winner') for m in created]
    if carry is not None:
        new_pool.append(carry)
    return created, new_pool


def _wb_round_real_losers(wb_round, round_number):
    """The (match, 'loser') sources a winners-bracket round actually feeds into the
    losers bracket. Only round 1 can have byes (see _seed_slots) — a bye match never
    produces a real loser, so it's excluded; from round 2 on every match is guaranteed
    two real players (their player1_id/player2_id just aren't filled in yet at
    bracket-construction time, so they can't be checked directly — every match counts)."""
    if round_number == 1:
        return [(m, 'loser') for m in wb_round if m.player1_id and m.player2_id]
    return [(m, 'loser') for m in wb_round]


def _build_losers_bracket(bracket, tournament, wb_rounds):
    """Build the losers bracket from the *actual* winners-bracket topology
    (`wb_rounds`, the per-round match lists from `_build_single_elim`), so it works
    whether or not WB round 1 had byes — the classic fixed seed-round/drop-in/merge
    sequence only works when every count involved is a clean power of two. One step per
    WB round: merge the current losers-bracket survivor pool with that round's real
    losers, then pair the merged pool down via `_pair_sources`. Once every WB round has
    fed in, keep pairing the surviving pool against itself (no more WB input) until
    exactly one player remains: the losers-bracket champion, who meets the winners-
    bracket champion in the grand final. A round that would pair zero real matches
    (a lone survivor with nothing to pair against) creates no Match rows and doesn't
    consume a round number — no phantom rounds.

    Returns the (match, role) source that produces the losers-bracket champion."""
    pool = []
    lb_round_number = 0

    def step(merged):
        nonlocal pool, lb_round_number
        created, pool = _pair_sources(bracket, tournament, Match.Side.LOSERS, lb_round_number + 1, merged)
        if created:
            lb_round_number += 1

    for round_number, wb_round in enumerate(wb_rounds, start=1):
        step(pool + _wb_round_real_losers(wb_round, round_number))

    while len(pool) > 1:
        step(pool)

    return pool[0]


def _fed_slots(matches):
    """{(match_pk, slot)} for every slot some other match feeds a player into."""
    fed = set()
    for m in matches:
        if m.next_match_id:
            fed.add((m.next_match_id, m.next_match_slot))
        if m.loser_next_match_id:
            fed.add((m.loser_next_match_id, m.loser_next_match_slot))
    return fed


def _is_bye_match(match, fed_slots):
    """True when this match can only ever have one player, so it is won without being
    played.

    A slot counts as real if a player is seeded into it *or* some upstream match feeds
    it. Testing `bool(player1_id) != bool(player2_id)` instead is wrong the moment
    results start landing: a round-2 match whose first player has already arrived from
    a completed round-1 bye has exactly one player set, but its other slot is fed by a
    real match still to be played. Treating that as a bye makes the edge free and
    understates how many games its participants will have played — which is precisely
    the accounting the 3-game guarantee is built on."""
    slot1 = match.player1_id is not None or (match.pk, 1) in fed_slots
    slot2 = match.player2_id is not None or (match.pk, 2) in fed_slots
    return slot1 != slot2


def bye_matches(bracket):
    """The matches in `bracket` that are byes — won without being played."""
    matches = list(Match.objects.filter(bracket=bracket))
    fed = _fed_slots(matches)
    return [m for m in matches if _is_bye_match(m, fed)]


def _topological_matches(bracket):
    """Every match in `bracket`, ordered so each match comes after all matches feeding
    it. Kahn's algorithm over the real `next_match`/`loser_next_match` edges.

    Ordering by (bracket_side, round_number) instead would happen to work for the
    graphs built today, but only because winners rounds are numbered before losers
    rounds and losers feed forward — an invariant held by convention in the builders
    rather than enforced anywhere. Any future format that feeds an edge "sideways"
    (a losers round into an equal-numbered round, a repechage, a consolation path back
    into the main tree) would silently break it, and the failure mode is quiet: a
    downstream match gets computed before its source and falls back to a default of 0.
    Sorting on the edges themselves removes the assumption entirely.

    Ties among matches that are ready at the same time are broken by
    (side, round, position) purely so the result is deterministic."""
    matches = list(Match.objects.filter(bracket=bracket))
    by_pk = {m.pk: m for m in matches}
    successors = {m.pk: [] for m in matches}
    indegree = {m.pk: 0 for m in matches}

    for m in matches:
        for target_id in (m.next_match_id, m.loser_next_match_id):
            if target_id in by_pk:
                successors[m.pk].append(target_id)
                indegree[target_id] += 1

    def sort_key(pk):
        m = by_pk[pk]
        return (m.bracket_side, m.round_number, m.position, pk)

    ready = [(sort_key(pk), pk) for pk, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)

    ordered = []
    while ready:
        _, pk = heapq.heappop(ready)
        ordered.append(by_pk[pk])
        for target_id in successors[pk]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                heapq.heappush(ready, (sort_key(target_id), target_id))

    if len(ordered) != len(matches):
        # Unreachable for any bracket this module builds; a cycle would mean a match
        # feeding itself, which must fail loudly rather than silently truncate.
        raise ValidationError({'detail': 'Bracket graph contains a cycle and cannot be evaluated.'})
    return ordered


def _min_real_games_before(bracket):
    """{match_pk: fewest real games any participant of that match can have played
    before it}.

    Derived from the actual graph rather than inferred from round numbers, because
    byes and losers-bracket carries mean two players arriving at the same match can
    have played different numbers of games. Traversing an edge costs 1 game if the
    source was a real match and 0 if it was a bye — that distinction is the whole
    point, and it is what makes "has this player had their three games?" answerable
    structurally instead of by hopeful convention."""
    ordered = _topological_matches(bracket)
    fed = _fed_slots(ordered)

    min_before = {}
    for match in ordered:
        min_before.setdefault(match.pk, 0)
        cost = 0 if _is_bye_match(match, fed) else 1
        arriving = min_before[match.pk] + cost
        for target_id in (match.next_match_id, match.loser_next_match_id):
            if target_id is None:
                continue
            current = min_before.get(target_id)
            min_before[target_id] = arriving if current is None else min(current, arriving)
    return min_before


def _attach_guarantee_matches(bracket, tournament):
    """Give a bonus match to anyone whose elimination would otherwise come before they
    have played `GUARANTEED_GAMES` real games.

    Losing a losers-bracket match is elimination, so for each such match the loser
    walks away having played `_min_real_games_before(match) + 1` games at minimum. Any
    match where that falls short of the guarantee gets its loser routed into a bonus
    match instead of straight out of the tournament.

    This replaces an earlier rule that only covered losers-bracket matches where *both*
    entrants were fresh winners-bracket dropouts. That rule missed real cases: a player
    who took a first-round bye, lost in winners round 2, and then lost to an
    established losers-bracket survivor had played just two games and was eliminated
    with no bonus match — verified against an 11-player field before this change.

    Bonus matches are dead ends (`next_match` stays NULL) and never re-enter the
    elimination tree. Because `loser_next_match` routes "whoever loses", not "whoever
    loses from a particular slot", a bonus match can occasionally be granted to a
    player already on three games — the guarantee is a floor, so an extra game
    honours it rather than breaking it."""
    min_before = _min_real_games_before(bracket)
    lb_matches = list(
        Match.objects.filter(bracket=bracket, bracket_side=Match.Side.LOSERS).order_by('round_number', 'position')
    )
    needy = [m for m in lb_matches if min_before.get(m.pk, 0) + 1 < GUARANTEED_GAMES]
    if len(needy) < 2:
        # Nothing to pair against — too small a field for a bonus match to exist.
        return []

    if len(needy) % 2 == 1:
        # An odd count would leave one qualifying player without an opponent. Pull in
        # the next-earliest losers-bracket match so everyone who needs a third game
        # gets one; its loser is the player who least "over-qualifies".
        spare = [m for m in lb_matches if m not in needy]
        spare.sort(key=lambda m: (min_before.get(m.pk, 0), m.round_number, m.position))
        if not spare:
            needy = needy[:-1]
        else:
            needy = needy + spare[:1]

    return _pair_losers(bracket, tournament, 1, needy, side=Match.Side.GUARANTEE)


def _attach_grand_final(bracket, tournament, wb_final_source, lb_final_source):
    grand_final = Match.objects.create(
        bracket=bracket, tournament=tournament, bracket_side=Match.Side.GRAND_FINAL, round_number=1, position=0,
    )
    _wire_source(grand_final, 1, wb_final_source)
    _wire_source(grand_final, 2, lb_final_source)
    return grand_final


@transaction.atomic
def generate_double_elimination_bracket(tournament):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    _require_minimum_players(players, 4, 'Double elimination')
    n = len(players)

    bracket_size = _next_power_of_two(n)
    total_rounds = bracket_size.bit_length() - 1
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=total_rounds, format=Bracket.Format.DOUBLE)

    wb_final, _, wb_rounds = _build_single_elim(bracket, tournament, players, bracket_side=Match.Side.WINNERS)
    lb_final_source = _build_losers_bracket(bracket, tournament, wb_rounds)
    _attach_grand_final(bracket, tournament, (wb_final, 'winner'), lb_final_source)
    return bracket


@transaction.atomic
def generate_three_game_guarantee_bracket(tournament):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    _require_minimum_players(players, 8, '3-game guarantee')
    n = len(players)

    bracket_size = _next_power_of_two(n)
    total_rounds = bracket_size.bit_length() - 1
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=total_rounds, format=Bracket.Format.GUARANTEE3)

    wb_final, _, wb_rounds = _build_single_elim(bracket, tournament, players, bracket_side=Match.Side.WINNERS)
    lb_final_source = _build_losers_bracket(bracket, tournament, wb_rounds)
    _attach_guarantee_matches(bracket, tournament)
    _attach_grand_final(bracket, tournament, (wb_final, 'winner'), lb_final_source)
    return bracket


def _round_robin_rounds(players):
    """Standard circle-method scheduler: pads with a bye slot if `players` is odd,
    returns a list of rounds, each a list of (p1, p2) pairs (bye pairings omitted)."""
    slots = list(players)
    if len(slots) % 2 == 1:
        slots.append(None)
    m = len(slots)

    rounds = []
    for _ in range(m - 1):
        pairs = []
        for i in range(m // 2):
            p1, p2 = slots[i], slots[m - 1 - i]
            if p1 is not None and p2 is not None:
                pairs.append((p1, p2))
        rounds.append(pairs)
        slots = [slots[0]] + [slots[-1]] + slots[1:-1]
    return rounds


@transaction.atomic
def generate_round_robin_bracket(tournament):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    _require_minimum_players(players, 2, 'Round robin')

    rounds = _round_robin_rounds(players)
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=len(rounds), format=Bracket.Format.ROUND_ROBIN)
    for round_number, pairs in enumerate(rounds, start=1):
        for position, (p1, p2) in enumerate(pairs):
            Match.objects.create(
                bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
                round_number=round_number, position=position, player1=p1, player2=p2, status=Match.Status.READY,
            )
    return bracket


def _played_pairs(tournament):
    """Every pair of players who have already met, as a set of frozensets — resolved in
    one query up front, since the pairing search below probes many candidate pairs and
    a per-probe database round trip would be wasteful."""
    pairs = set()
    for p1_id, p2_id in Match.objects.filter(tournament=tournament).values_list('player1_id', 'player2_id'):
        if p1_id and p2_id:
            pairs.add(frozenset((p1_id, p2_id)))
    return pairs


def _adjacent_pairs(pool):
    return [(pool[i], pool[i + 1]) for i in range(0, len(pool) - 1, 2)]


def _swiss_pairings(ranked, played_pairs, score_of):
    """Pair one Swiss round from `ranked` (best-first, even length).

    Two goals, in strict priority order:

    1. **Never repeat a pairing that can be avoided.** Enforced by a complete
       backtracking search: if any rematch-free perfect pairing of the field exists,
       one is found. Note the precise contract — *avoidable* repeats never happen, but
       repeats are not impossible. Once enough rounds have been played (a small field
       going deep, say six players over four rounds), every remaining pairing may be a
       repeat; the search then returns nothing and the fallback below pairs adjacently,
       permitting rematches as a genuine last resort rather than failing to produce a
       round at all.
    2. **Pair players on the same score.** This is the soft goal, expressed through the
       order candidates are tried rather than as a constraint — each player's opponents
       are tried in increasing score difference, so a same-score opponent is always
       attempted before a cross-score one, and cross-score pairings ("floats") happen
       only where the search needs them to satisfy goal 1.

    Treating score groups as a hard constraint instead is what an earlier version did,
    and it was wrong: with five players it forced a third-round rematch inside the
    1-point group while an entirely rematch-free pairing of the field was available.
    Standard Swiss practice floats across scores to avoid a repeat, not the reverse.

    Within a block of equal scores the preferred opponent is the one opposite in the
    standard "Dutch" split — top half against bottom half, so a group of eight pairs
    1v5 2v6 3v7 4v8 rather than 1v2 3v4, which would knock the strongest players out
    of contention against each other immediately. Ties break by index, so the result is
    fully deterministic for a given standings order.

    Scope, stated plainly: this is a sound Swiss pairing for this platform, not an
    implementation of any federation's official rules. It does not model colours or
    side balance (the data model has no notion of them), float direction across
    rounds, accelerated pairings, or forbidden-pairing rules beyond "have these two
    already met". Adding any of those means extending the candidate ordering here
    rather than restructuring the search.

    Returns pairs; falls back to adjacent pairing (which may contain rematches) when no
    rematch-free pairing exists, or in the pathological case where the search exceeds
    `SEARCH_NODE_BUDGET`."""
    pool = list(ranked)
    return _search_pairing(pool, played_pairs, score_of, [SEARCH_NODE_BUDGET]) or _adjacent_pairs(pool)


#: Node ceiling for the pairing search. Measured cost is far below this: a normal Swiss
#: event (log2(n) rounds) explores ~77 nodes at 128 players, and even a field pushed to
#: full round-robin saturation — 20 players over 19 rounds, where everyone has already
#: played everyone — peaks around 2,000 nodes and 1ms, because the preferred candidate
#: is almost always legal and backtracking rarely engages. The ceiling exists so that a
#: pathological rematch graph degrades into a fallback pairing instead of stalling a
#: request; it is not expected to be reached.
SEARCH_NODE_BUDGET = 200_000


def _search_pairing(pool, played_pairs, score_of, budget):
    if not pool:
        return []
    if budget[0] <= 0:
        return None
    budget[0] -= 1

    first, rest = pool[0], pool[1:]
    first_score = score_of(first)
    # Ideal same-score opponent: the one directly opposite in the Dutch split of this
    # player's score block.
    #
    # `ideal` indexes into `rest` (everyone remaining) rather than into the score block,
    # which looks wrong but is not: `pool` arrives ranked and every recursive call
    # preserves that order, so `pool[0]` always holds the top score and its block always
    # occupies the head of `rest`. Positions 0..block_size-2 are therefore exactly the
    # block, and the arithmetic lands inside it. Blocks of 4 pair 1v3 2v4; blocks of 8
    # pair 1v5 2v6 3v7 4v8 — see the Dutch-split tests, which cover the multi-block case
    # precisely because this reasoning is not obvious from the expression alone.
    block_size = 1 + sum(1 for p in rest if score_of(p) == first_score)
    ideal = max(block_size // 2 - 1, 0)

    def preference(index):
        return abs(first_score - score_of(rest[index])), abs(index - ideal), index

    for index in sorted(range(len(rest)), key=preference):
        candidate = rest[index]
        if frozenset((first.pk, candidate.pk)) in played_pairs:
            continue
        sub = _search_pairing(rest[:index] + rest[index + 1:], played_pairs, score_of, budget)
        if sub is not None:
            return [(first, candidate)] + sub
    return None


def _swiss_bye_counts(tournament):
    """How many automatic byes each player has already received in this tournament's
    Swiss bracket (a completed Match with no player2) — used to spread byes around
    fairly instead of always giving them to whoever falls out of the pairing loop."""
    counts = {}
    for m in Match.objects.filter(tournament=tournament, bracket_side=Match.Side.WINNERS, player2__isnull=True):
        counts[m.player1_id] = counts.get(m.player1_id, 0) + 1
    return counts


@transaction.atomic
def _create_swiss_round(bracket, tournament, round_number, ranked_players, scores=None):
    """Build one Swiss round from `ranked_players` (best-first by current standings),
    pairing within score groups — see `_swiss_pairings`.

    An odd field means one player sits out with an automatic bye. It goes to whoever
    has had the fewest byes so far, breaking ties toward the lowest-ranked player,
    which is the conventional choice and keeps a single player from absorbing every
    bye while others have had none. A bye scores like a win (standard Swiss practice)
    but is never counted as an opponent, so it cannot distort the Buchholz-style
    tiebreaks in `standings`."""
    pool = list(ranked_players)
    scores = scores or {p.pk: 0 for p in pool}

    bye_player = None
    if len(pool) % 2 == 1:
        bye_counts = _swiss_bye_counts(tournament)
        rank = {p.pk: i for i, p in enumerate(pool)}
        bye_player = min(pool, key=lambda p: (bye_counts.get(p.pk, 0), -rank[p.pk]))
        pool = [p for p in pool if p.pk != bye_player.pk]

    pairs = _swiss_pairings(pool, _played_pairs(tournament), lambda p: scores.get(p.pk, 0))

    for position, (p1, p2) in enumerate(pairs):
        Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
            round_number=round_number, position=position, player1=p1, player2=p2, status=Match.Status.READY,
        )

    if bye_player is not None:
        bye_match = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
            round_number=round_number, position=len(pairs), player1=bye_player, status=Match.Status.READY,
        )
        complete_match(bye_match, bye_player)


def swiss_round_count(n, configured=None):
    """How many rounds a Swiss event of `n` players runs.

    `ceil(log2(n))` is the usual default: enough rounds for exactly one player to
    plausibly remain unbeaten. It is a policy choice rather than a theorem, though —
    it does not guarantee a clean separation once ties and tiebreaks are involved, and
    organisers often prefer an extra round. `configured` therefore overrides it, and
    this is the only place the default lives."""
    if configured:
        return max(1, int(configured))
    return max(1, math.ceil(math.log2(n)))


@transaction.atomic
def generate_swiss_bracket(tournament, total_rounds=None):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    _require_minimum_players(players, 2, 'Swiss')
    n = len(players)

    # An explicit argument wins; otherwise use a `swiss_rounds` field on the tournament
    # if one is ever added, and fall back to the ceil(log2(n)) default.
    configured = total_rounds if total_rounds is not None else getattr(tournament, 'swiss_rounds', None)
    bracket = Bracket.objects.create(
        tournament=tournament, total_rounds=swiss_round_count(n, configured), format=Bracket.Format.SWISS,
    )
    # Round 1: everyone is on zero, so this is a single score group and the Dutch split
    # pairs the top half against the bottom half.
    _create_swiss_round(bracket, tournament, 1, players)
    return bracket


@transaction.atomic
def generate_next_swiss_round(bracket):
    """Pair and create the next Swiss round.

    The bracket row is locked first. Deciding "the current round is complete, so build
    the next one" is a read followed by a write, and two simultaneous requests can both
    read the same completed round and both build round N+1 — duplicating an entire
    round of pairings. The unique constraint on
    (bracket, side, round_number, position) would reject the second insert, but only
    after the pairing work, and as a 500 rather than a clear error. Locking makes the
    second request wait and then correctly observe that the round already exists."""
    if bracket.format != Bracket.Format.SWISS:
        raise ValidationError({'detail': 'This bracket is not a Swiss bracket.'})

    _lock_tournament(bracket.tournament_id)
    bracket = _lock_bracket(bracket.pk)
    tournament = bracket.tournament
    matches = list(Match.objects.filter(bracket=bracket))
    current_round = max(m.round_number for m in matches)
    if any(m.status != Match.Status.COMPLETED for m in matches if m.round_number == current_round):
        raise ValidationError({'detail': f'Round {current_round} is not finished yet.'})
    if current_round >= bracket.total_rounds:
        raise ValidationError({'detail': 'This Swiss bracket has already reached its final round.'})

    # Rank with the Swiss tiebreak chain (median-Buchholz first), so the score groups
    # the next round is built from are ordered by genuine standing rather than by
    # registration order among equal scores.
    rows = standings(tournament, tiebreakers=FORMAT_TIEBREAKERS[Bracket.Format.SWISS])
    ranked_players = [row['player'] for row in rows]
    scores = {row['player'].pk: row['wins'] for row in rows}
    _create_swiss_round(bracket, tournament, current_round + 1, ranked_players, scores=scores)
    return bracket


@transaction.atomic
def generate_group_playoff_bracket(tournament, num_groups=None):
    _require_no_existing_bracket(tournament)
    players = seed_players(tournament)
    n = len(players)
    if num_groups is None:
        num_groups = max(2, round(n / 4)) if n else 2
    else:
        try:
            num_groups = max(2, int(num_groups))
        except (TypeError, ValueError):
            raise ValidationError({'num_groups': 'Must be a whole number.'})
    if num_groups > 26:
        # Labels are single letters A-Z; past that `chr(ord('A') + i)` starts emitting
        # punctuation rather than group names.
        raise ValidationError({'detail': 'A group stage supports at most 26 groups (A-Z).'})
    if n < 2 * num_groups:
        raise ValidationError({
            'detail': f'Need at least {2 * num_groups} registered players for {num_groups} groups — you have {n}.',
        })

    labels = [chr(ord('A') + i) for i in range(num_groups)]
    groups = {label: [] for label in labels}
    # Snake/serpentine distribution (A,B,C,D, D,C,B,A, A,B,C,D, ...) so seed strength is
    # balanced across groups, not just headcount — straight `i % num_groups` assignment
    # stacks all the top seeds into group A.
    for i, p in enumerate(players):
        offset = i % num_groups
        forward_pass = (i // num_groups) % 2 == 0
        label_index = offset if forward_pass else num_groups - 1 - offset
        groups[labels[label_index]].append(p)

    group_rounds = {label: _round_robin_rounds(group_players) for label, group_players in groups.items()}
    max_rounds = max(len(r) for r in group_rounds.values())

    bracket = Bracket.objects.create(tournament=tournament, total_rounds=max_rounds, format=Bracket.Format.GROUP_PLAYOFF)

    for round_number in range(1, max_rounds + 1):
        position = 0
        for label in labels:
            rounds = group_rounds[label]
            if round_number > len(rounds):
                continue
            for p1, p2 in rounds[round_number - 1]:
                Match.objects.create(
                    bracket=bracket, tournament=tournament, bracket_side=Match.Side.GROUP, group_label=label,
                    round_number=round_number, position=position, player1=p1, player2=p2, status=Match.Status.READY,
                )
                position += 1

    return bracket


def _seed_first_round_pairs(size):
    """The seed numbers that meet in round 1 of a `size` bracket, e.g. size 8 ->
    [(1,8), (4,5), (2,7), (3,6)]."""
    order = _seed_order(size)
    return [(order[2 * i], order[2 * i + 1]) for i in range(size // 2)]


def _avoid_same_group_first_round(entries, node_budget=50000):
    """Order playoff qualifiers so no first-round match is a same-group rematch.

    `entries` is [(player, group_label)] in placement-first seed order: every group
    winner, then every runner-up, and so on. That ordering alone resolves the common
    balanced cases — with four groups of two qualifiers it already puts each runner-up
    opposite a different group's winner — but it cannot always. With three groups the
    bracket has byes and the remaining slots may force a same-group pairing.

    Seeds are therefore assigned by backtracking search rather than by repairing
    conflicts greedily. A greedy repair only accepts a swap that strictly reduces the
    conflict count, so it stalls in local minima and can report a conflict where a
    conflict-free arrangement exists; the field here is small (qualifiers, not
    entrants), so an exhaustive search is affordable and gives a real guarantee: if a
    conflict-free assignment exists, one is found.

    Candidates are tried in placement order at every step, so the search only departs
    from ideal seeding where a conflict forces it, and the first solution found is the
    one closest to the natural seeding. Deterministic. `node_budget` bounds pathological
    searches; exhausting it (or genuine infeasibility) falls back to placement order,
    which is a fair arrangement that merely fails to dodge every rematch."""
    count = len(entries)
    partner = {}
    for a, b in _seed_first_round_pairs(_next_power_of_two(count)):
        partner[a], partner[b] = b, a

    assignment = [None] * (count + 1)  # seed number -> index into `entries`
    used = [False] * count
    budget = [node_budget]

    def assign(seed):
        if seed > count:
            return True
        if budget[0] <= 0:
            return False
        budget[0] -= 1

        opposing_seed = partner.get(seed)
        opposing = (
            entries[assignment[opposing_seed]][1]
            if opposing_seed is not None and opposing_seed <= count and assignment[opposing_seed] is not None
            else None
        )
        for index in range(count):
            if used[index] or entries[index][1] == opposing:
                continue
            used[index], assignment[seed] = True, index
            if assign(seed + 1):
                return True
            used[index], assignment[seed] = False, None
        return False

    if assign(1):
        return [entries[assignment[seed]][0] for seed in range(1, count + 1)]
    return [player for player, _ in entries]


@transaction.atomic
def generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=1):
    if bracket.format != Bracket.Format.GROUP_PLAYOFF:
        raise ValidationError({'detail': 'This bracket is not a group + playoff bracket.'})
    if qualifiers_per_group < 1:
        raise ValidationError({'detail': 'At least one player per group must qualify.'})

    # Locked for the same reason as the Swiss round builder: "the group stage is over
    # and no playoff exists yet" is a read that two requests can pass simultaneously,
    # each then building a playoff bracket. Tournament first, per the LOCK ORDER note.
    _lock_tournament(bracket.tournament_id)
    bracket = _lock_bracket(bracket.pk)
    tournament = bracket.tournament
    group_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP)
    if group_matches.filter(status__in=[Match.Status.PENDING, Match.Status.READY]).exists():
        raise ValidationError({'detail': 'The group stage is not finished yet.'})
    if Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS).exists():
        raise ValidationError({'detail': 'The playoff bracket has already been generated.'})

    all_players = seed_players(tournament)
    labels = sorted(set(group_matches.values_list('group_label', flat=True)))

    qualifiers_by_group = {}
    for label in labels:
        ids_in_group = set()
        for m in group_matches.filter(group_label=label):
            ids_in_group.add(m.player1_id)
            ids_in_group.add(m.player2_id)
        group_players = [p for p in all_players if p.pk in ids_in_group]
        table = group_stage_standings(tournament, group_players)
        qualifiers_by_group[label] = [row['player'] for row in table[:qualifiers_per_group]]

    # Placement-first, then group: all group winners are seeded above all runners-up,
    # rather than listing each group's qualifiers together (which would seed a group
    # winner and their own runner-up as seeds 1 and 2).
    entries = [
        (qualifiers_by_group[label][place], label)
        for place in range(qualifiers_per_group)
        for label in labels
        if place < len(qualifiers_by_group[label])
    ]
    if not entries:
        raise ValidationError({'detail': 'No qualifiers could be determined from the group stage.'})

    _build_single_elim(
        bracket, tournament, _avoid_same_group_first_round(entries), bracket_side=Match.Side.WINNERS,
    )
    return bracket


def get_tournament_champion(tournament):
    """Return the User who has won `tournament` outright, or None if its bracket
    doesn't exist yet or isn't decided yet. "Decided" depends on format:
    - single elimination / group+playoff (post phase-2): the one match with no
      next_match — the root of the elimination tree — is COMPLETED.
    - double elimination / 3-game guarantee: the grand final match is COMPLETED.
    - round robin: every match is COMPLETED (round robin schedules every round
      upfront — see _round_robin_rounds — so "all done" is a genuine finish,
      not just the end of one round); champion is the top standings entry.
    - swiss: the bracket's final round (bracket.total_rounds) exists and every
      match in it is COMPLETED; champion is the top standings entry.
    """
    bracket = getattr(tournament, 'bracket', None)
    if bracket is None:
        return None

    if bracket.format in (Bracket.Format.SINGLE, Bracket.Format.GROUP_PLAYOFF):
        final_match = Match.objects.filter(
            bracket=bracket, bracket_side=Match.Side.WINNERS, next_match__isnull=True,
        ).first()
        return final_match.winner if final_match and final_match.status == Match.Status.COMPLETED else None

    if bracket.format in (Bracket.Format.DOUBLE, Bracket.Format.GUARANTEE3):
        return _double_elimination_champion(bracket)

    if bracket.format == Bracket.Format.ROUND_ROBIN:
        matches = Match.objects.filter(bracket=bracket)
        if not matches.exists() or matches.exclude(status=Match.Status.COMPLETED).exists():
            return None
        ranked = format_standings(tournament)
        return ranked[0]['player'] if ranked else None

    if bracket.format == Bracket.Format.SWISS:
        final_round = Match.objects.filter(bracket=bracket, round_number=bracket.total_rounds)
        if not final_round.exists() or final_round.exclude(status=Match.Status.COMPLETED).exists():
            return None
        ranked = format_standings(tournament)
        return ranked[0]['player'] if ranked else None

    return None


def _double_elimination_champion(bracket):
    """The grand final only settles the title if the winners-bracket finalist wins it;
    otherwise both players hold one loss and the reset decides. Guarantee matches are
    ignored here — they are consolation games and never affect the title."""
    grand_finals = list(
        Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL).order_by('round_number')
    )
    if not grand_finals:
        return None

    first = grand_finals[0]
    if first.status != Match.Status.COMPLETED:
        return None
    if first.winner_id == first.player1_id:
        return first.winner  # WB finalist won unbeaten

    reset = grand_finals[1] if len(grand_finals) > 1 else None
    if reset is None or reset.status != Match.Status.COMPLETED:
        return None
    return reset.winner


@transaction.atomic
def finalize_tournament_champion(tournament):
    """Persist the tournament's champion (idempotent — a champion, once set, is
    never recomputed or overwritten) and send the win email the first time it's
    decided. Call this after every match result submission; it's a no-op for
    every call that doesn't happen to be the tournament-deciding one.

    The tournament row is locked so that idempotency actually holds under concurrency.
    Without it two requests can both read a NULL champion, both resolve the same
    winner, and both queue a congratulations email — the database ends up correct but
    the champion is told twice. The lock makes the second request observe the first's
    write and return early."""
    # Usually already held (match completion takes it first), in which case this is a
    # no-op; it is taken here too so that direct callers are equally safe.
    locked = _lock_tournament(tournament.pk)
    if locked.champion_id:
        tournament.champion_id = locked.champion_id
        return locked.champion

    champion = get_tournament_champion(locked)
    if champion is None:
        return None

    tournament = locked

    tournament.champion = champion
    tournament.champion_declared_at = timezone.now()
    tournament.save(update_fields=['champion', 'champion_declared_at'])

    # Deferred until the surrounding transaction commits. This is usually called from
    # inside match completion, so sending inline risks both failure directions: an
    # email congratulating a champion whose row was rolled back, and — worse — a mail
    # backend raising and rolling back a perfectly good match result. on_commit runs
    # only once the champion is durably stored, and never affects the transaction.
    from tourny_regist.emails import send_tournament_win_email
    transaction.on_commit(lambda: send_tournament_win_email(tournament, champion))
    return champion


class NeedsAdminReview(Exception):
    """Raised by reset_bracket when real results already exist, so the caller
    (brackets.views) can file a core.models.AdminReviewRequest instead of
    resetting directly. Deliberately a separate class from
    tourny_regist.lifecycle.NeedsAdminReview rather than importing it — this
    module already depends on tourny_regist.models at import time, but tying
    a plain marker exception to that module too would be an import for
    duck-typing's sake. Callers of either match on the class name/behavior,
    not on shared ancestry."""


def _is_safe_to_reset(bracket):
    """True when every COMPLETED match in `bracket` is a bye — i.e. no real
    result has been recorded yet, so tearing the bracket down loses no
    competitive result. Byes auto-complete at generation time (see
    _build_single_elim), so a freshly-generated bracket already has some
    COMPLETED matches even with zero games actually played — bye_matches()
    is what tells the two apart."""
    bye_ids = {m.pk for m in bye_matches(bracket)}
    return not Match.objects.filter(
        bracket=bracket, status=Match.Status.COMPLETED,
    ).exclude(pk__in=bye_ids).exists()


@transaction.atomic
def reset_bracket(tournament, actor, reason, *, bypass_safety_check=False):
    """Deletes the current bracket and all its matches — safe self-service
    only when every completed match is a bye (see _is_safe_to_reset);
    otherwise raises NeedsAdminReview. Does not regenerate anything; the
    caller re-invokes the appropriate generate_*_bracket afterward, which is
    also how "reseed" and "regenerate" are implemented — as reset followed by
    a normal (re-)generation call — rather than as separate primitives that
    would duplicate this one's safety logic.

    Locks Tournament then Bracket, per the LOCK ORDER note at the top of this
    module (no new select_for_update() site — both locks go through the
    existing helpers, so LockOrderAuditTests needs no new APPROVED_SITES
    entry for this function). No Match row is individually locked; this is a
    bulk delete, not a row-by-row mutation, and holding the Tournament lock
    for the whole transaction is what prevents a concurrent complete_match
    from racing the safety check — that function takes the same lock first,
    so it either finishes (and this reset correctly sees its result and
    refuses) or waits (and finds no bracket left once it proceeds, failing
    its own re-read of the match)."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A reason for resetting the bracket is required.'})

    _lock_tournament(tournament.pk)
    try:
        bracket = Bracket.objects.get(tournament=tournament)
    except Bracket.DoesNotExist:
        raise ValidationError({'detail': 'This tournament has no bracket to reset.'})
    bracket = _lock_bracket(bracket.pk)

    if not bypass_safety_check and not _is_safe_to_reset(bracket):
        raise NeedsAdminReview()

    previous_format = bracket.format
    Match.objects.filter(bracket=bracket).delete()
    bracket.delete()

    if tournament.champion_id:
        tournament.champion = None
        tournament.champion_declared_at = None
        tournament.save(update_fields=['champion', 'champion_declared_at'])

    from core.audit import log_action
    log_action(actor, 'bracket.reset', tournament, reason=reason, previous_format=previous_format)
    return previous_format


def _downstream_reachable(match):
    """Every match reachable forward from `match` via next_match/loser_next_match,
    locked as they're visited — used only by override_match_result's safety check,
    which needs a consistent read of "has anything downstream already been decided"
    under the same transaction that's about to mutate this match's placement."""
    seen = {}
    queue = [match.next_match_id, match.loser_next_match_id]
    while queue:
        target_id = queue.pop()
        if target_id is None or target_id in seen:
            continue
        target = Match.objects.select_for_update().get(pk=target_id)
        seen[target_id] = target
        queue.append(target.next_match_id)
        queue.append(target.loser_next_match_id)
    return seen


@transaction.atomic
def override_match_result(match, actor, new_winner, new_score, reason):
    """Correct a completed match's recorded winner/score — for a genuine data-entry
    mistake caught before anything was built on top of it, not a substitute for
    reset_bracket. Safe exactly when nothing downstream of this match has a recorded
    result yet: in that case the old winner's (and, for double-elim, old loser's)
    placement into the next match(es) can be retracted and redone with the corrected
    winner, because no one has played on the strength of the old placement.

    If something downstream is already COMPLETED, retracting here would silently
    invalidate that real result rather than fix anything — refuses outright rather
    than inventing a cascading-undo, and tells the caller to use reset_bracket (which
    already has its own admin-review escalation) instead. Round robin and Swiss
    matches never chain via next_match, so this safety check is always trivially
    satisfied for them — overriding one of their results only ever risks the
    tournament's champion, corrected below the same way reset_bracket clears it."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A reason for overriding this result is required.'})

    tournament = _lock_tournament(match.tournament_id)
    locked = Match.objects.select_for_update().get(pk=match.pk)

    if locked.status != Match.Status.COMPLETED:
        raise ValidationError({'detail': 'Only a completed match can have its result overridden.'})

    new_winner_id = new_winner.pk if new_winner is not None else None
    if new_winner_id is None or new_winner_id not in (locked.player1_id, locked.player2_id):
        raise ValidationError({'winner': 'The winner must be one of the players in this match.'})
    if new_winner_id == locked.winner_id:
        raise ValidationError({'detail': 'That player is already recorded as the winner.'})
    if locked.player1_id is None or locked.player2_id is None:
        raise ValidationError({'detail': 'A bye has no result to override.'})

    downstream = _downstream_reachable(locked)
    if any(m.status == Match.Status.COMPLETED for m in downstream.values()):
        raise ValidationError({
            'detail': 'This match has already fed into a completed downstream match, so overriding it '
                      'here would silently invalidate that result. Reset the bracket and replay from '
                      'this point instead.',
        })

    old_winner_id = locked.winner_id
    old_score = locked.score
    old_loser_id = locked.player2_id if locked.player1_id == old_winner_id else locked.player1_id
    new_loser_id = locked.player2_id if locked.player1_id == new_winner_id else locked.player1_id

    _retract_from(locked.next_match_id, locked.next_match_slot, old_winner_id)
    _retract_from(locked.loser_next_match_id, locked.loser_next_match_slot, old_loser_id)

    locked.winner_id = new_winner_id
    locked.score = new_score
    locked.save(update_fields=['winner', 'score'])

    _advance_into(locked.next_match_id, locked.next_match_slot, new_winner_id)
    _advance_into(locked.loser_next_match_id, locked.loser_next_match_slot, new_loser_id)
    _open_grand_final_reset_if_needed(locked, new_winner_id)

    # Idempotency (finalize_tournament_champion never recomputes a champion once set)
    # means a stale champion from the old result must be explicitly cleared before
    # recomputing — otherwise a correction that changes who actually won would leave
    # the wrong player declared. Safe to do unconditionally: if the champion wasn't
    # decided by this match, get_tournament_champion just re-derives the same answer.
    if tournament.champion_id:
        tournament.champion = None
        tournament.champion_declared_at = None
        tournament.save(update_fields=['champion', 'champion_declared_at'])

    match.winner_id = new_winner_id
    match.score = new_score

    from core.audit import log_action
    log_action(
        actor, 'match.result_overridden', tournament, reason=reason,
        match_id=match.pk, old_winner_id=old_winner_id, new_winner_id=new_winner_id,
        old_score=old_score, new_score=new_score,
    )
    finalize_tournament_champion(tournament)
    return locked


@transaction.atomic
def forfeit_match(match, actor, forfeiting_player, reason):
    """Award the match to whichever player didn't forfeit, tagging it distinctly from
    a played result (is_forfeit/forfeited_by) so bracket UIs and standings can show it
    honestly. Reuses complete_match for the actual advancement and locking rather than
    duplicating either — deliberately does NOT take its own Match lock first (that
    would lock Match before complete_match takes the Tournament lock internally,
    inverting the LOCK ORDER at the top of this module). Pre-validation here reads the
    unlocked `match` instance, the same way MatchResultView does before calling
    complete_match; the authoritative checks (already completed, winner not a real
    participant) happen under complete_match's own lock regardless."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A reason for the forfeit is required.'})
    if match.status != Match.Status.READY:
        raise ValidationError({
            'detail': 'This match is not ready for a forfeit (players not yet determined, or already completed).',
        })
    if match.player1_id is None or match.player2_id is None:
        raise ValidationError({'detail': 'A bye has no opponent to forfeit against.'})

    forfeiting_id = forfeiting_player.pk if forfeiting_player is not None else None
    if forfeiting_id not in (match.player1_id, match.player2_id):
        raise ValidationError({'forfeiting_player': 'The forfeiting player must be one of the players in this match.'})

    winner_id = match.player2_id if match.player1_id == forfeiting_id else match.player1_id
    winner = match.player1 if winner_id == match.player1_id else match.player2

    completed = complete_match(match, winner, score='Forfeit')
    completed.is_forfeit = True
    completed.forfeited_by_id = forfeiting_id
    completed.save(update_fields=['is_forfeit', 'forfeited_by'])

    from core.audit import log_action
    log_action(actor, 'match.forfeited', match.tournament, reason=reason, match_id=match.pk, forfeiting_player_id=forfeiting_id)
    finalize_tournament_champion(match.tournament)

    match.winner_id = winner_id
    match.score = 'Forfeit'
    match.status = Match.Status.COMPLETED
    match.is_forfeit = True
    match.forfeited_by_id = forfeiting_id
    return match


def disqualify_player_from_bracket(tournament, player, actor, reason):
    """Called after tourny_regist.lifecycle.disqualify_registration marks the
    registration itself DISQUALIFIED — this handles the bracket-side consequence: any
    match `player` is currently READY to play is auto-forfeited in their opponent's
    favor.

    A player only ever occupies at most one live match at a time in an elimination
    bracket (their next match's slot stays empty until they win forward into it), but
    round robin/Swiss schedule every remaining match up front, so this walks *every*
    READY match they're in rather than assuming just one. PENDING matches are left
    alone — a match missing its second player isn't theirs to forfeit yet, and will
    resolve normally once (if ever) that slot fills."""
    matches = list(Match.objects.filter(
        tournament=tournament, status=Match.Status.READY,
    ).filter(Q(player1=player) | Q(player2=player)))
    forfeited = []
    for match in matches:
        forfeited.append(forfeit_match(match, actor, player, reason))
    return forfeited
