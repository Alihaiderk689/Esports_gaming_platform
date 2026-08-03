import math

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from brackets.models import Bracket, Match


def _checked_in_players(tournament):
    """Only checked-in registrations are eligible to be seeded into a bracket —
    no-shows who registered but never checked in are excluded."""
    return [
        r.player for r in tournament.registrations.filter(checked_in=True).order_by('registered_at')
    ]


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


def complete_match(match, winner, score=''):
    loser = match.player2 if match.player1_id == winner.pk else match.player1

    match.winner = winner
    match.score = score
    match.status = Match.Status.COMPLETED
    match.save(update_fields=['winner', 'score', 'status'])

    next_match = match.next_match
    if next_match is not None:
        if match.next_match_slot == 1:
            next_match.player1 = winner
        else:
            next_match.player2 = winner
        if next_match.player1_id and next_match.player2_id:
            next_match.status = Match.Status.READY
        next_match.save()

    loser_next_match = match.loser_next_match
    if loser_next_match is not None and loser is not None:
        if match.loser_next_match_slot == 1:
            loser_next_match.player1 = loser
        else:
            loser_next_match.player2 = loser
        if loser_next_match.player1_id and loser_next_match.player2_id:
            loser_next_match.status = Match.Status.READY
        loser_next_match.save()


def standings(tournament, players=None):
    """Rank `players` (defaults to every checked-in player) by completed-match win
    count, ties broken by original registration order. Returns
    [{'player': User, 'wins': int, 'played': int}, ...]."""
    if players is None:
        players = _checked_in_players(tournament)

    wins = {p.pk: 0 for p in players}
    played = {p.pk: 0 for p in players}
    for m in Match.objects.filter(tournament=tournament, status=Match.Status.COMPLETED):
        for pid in (m.player1_id, m.player2_id):
            if pid in played:
                played[pid] += 1
        if m.winner_id in wins:
            wins[m.winner_id] += 1

    order = {p.pk: i for i, p in enumerate(players)}
    ranked = sorted(players, key=lambda p: (-wins[p.pk], order[p.pk]))
    return [{'player': p, 'wins': wins[p.pk], 'played': played[p.pk]} for p in ranked]


def _build_single_elim(bracket, tournament, players, bracket_side=Match.Side.WINNERS):
    """Build a full single-elimination tree for `players` (seeded and padded with byes
    to the next power of two — see `_seed_slots`), tagged with `bracket_side`. Byes are
    auto-completed once the tree is wired up, advancing that player with no action
    needed from anyone. Returns (final_match, total_rounds)."""
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

    current_round_matches = round_matches
    for round_number in range(2, total_rounds + 1):
        current_round_matches = _pair_winners(bracket, tournament, bracket_side, round_number, current_round_matches)

    final_match = current_round_matches[0] if current_round_matches else round_matches[0]

    # Round-1 byes: with proper seeding (see _seed_slots) a pairing can never be two
    # byes facing each other, so exactly one of these branches applies per bye match.
    for match in round_matches:
        if match.player1_id and not match.player2_id:
            complete_match(match, match.player1, score='BYE')
        elif match.player2_id and not match.player1_id:
            complete_match(match, match.player2, score='BYE')

    return final_match, total_rounds


def generate_bracket(tournament):
    players = _checked_in_players(tournament)
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


def _drop_in(bracket, tournament, round_number, survivors, wb_losers):
    """Merge losers-bracket survivors (their *winner*) with a fresh batch of winners-bracket
    losers (their *loser*), one-to-one, into a new losers-bracket round."""
    created = []
    for i, (surv, wbm) in enumerate(zip(survivors, wb_losers)):
        m = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.LOSERS, round_number=round_number, position=i,
        )
        created.append(m)
        surv.next_match = m
        surv.next_match_slot = 1
        surv.save(update_fields=['next_match', 'next_match_slot'])
        wbm.loser_next_match = m
        wbm.loser_next_match_slot = 2
        wbm.save(update_fields=['loser_next_match', 'loser_next_match_slot'])
    return created


def _build_double_elim_core(bracket, tournament, players):
    """Build the winners bracket and losers bracket (through the LB final) shared by
    Double Elimination and 3-Game Guarantee. Returns
    {'wb_final': Match, 'lb_seed_matches': [Match, ...], 'lb_final': Match}."""
    n = len(players)
    k = n.bit_length() - 1

    wb_rounds = []
    round_matches = []
    for i in range(n // 2):
        p1, p2 = players[2 * i], players[2 * i + 1]
        m = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
            round_number=1, position=i, player1=p1, player2=p2, status=Match.Status.READY,
        )
        round_matches.append(m)
    wb_rounds.append(round_matches)
    current = round_matches
    for round_number in range(2, k + 1):
        current = _pair_winners(bracket, tournament, Match.Side.WINNERS, round_number, current)
        wb_rounds.append(current)
    wb_final = wb_rounds[-1][0]

    # Losers bracket — seed round pairs up WB round-1 losers directly; every subsequent
    # winners-bracket round's losers "drop in" against the current losers-bracket
    # survivors, with a merge round in between whenever the survivor count needs halving
    # before the next drop-in can pair 1:1.
    lb_round_number = 1
    lb_seed_matches = _pair_losers(bracket, tournament, lb_round_number, wb_rounds[0])
    lb_current = lb_seed_matches
    lb_round_number += 1

    for wb_round_idx in range(1, k):
        lb_current = _drop_in(bracket, tournament, lb_round_number, lb_current, wb_rounds[wb_round_idx])
        lb_round_number += 1
        if wb_round_idx < k - 1 and len(lb_current) > 1:
            lb_current = _pair_winners(bracket, tournament, Match.Side.LOSERS, lb_round_number, lb_current)
            lb_round_number += 1

    lb_final = lb_current[0]

    return {'wb_final': wb_final, 'lb_seed_matches': lb_seed_matches, 'lb_final': lb_final}


def _attach_grand_final(bracket, tournament, wb_final, lb_final):
    grand_final = Match.objects.create(
        bracket=bracket, tournament=tournament, bracket_side=Match.Side.GRAND_FINAL, round_number=1, position=0,
    )
    wb_final.next_match = grand_final
    wb_final.next_match_slot = 1
    wb_final.save(update_fields=['next_match', 'next_match_slot'])
    lb_final.next_match = grand_final
    lb_final.next_match_slot = 2
    lb_final.save(update_fields=['next_match', 'next_match_slot'])
    return grand_final


def generate_double_elimination_bracket(tournament):
    players = _checked_in_players(tournament)
    n = len(players)
    if n < 4 or (n & (n - 1)) != 0:
        raise ValidationError({
            'detail': (
                f'Double elimination needs an exact power of two players '
                f'(4, 8, 16, or 32) — you have {n} registered.'
            ),
        })

    k = n.bit_length() - 1
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=k, format=Bracket.Format.DOUBLE)
    core = _build_double_elim_core(bracket, tournament, players)
    _attach_grand_final(bracket, tournament, core['wb_final'], core['lb_final'])
    return bracket


def generate_three_game_guarantee_bracket(tournament):
    players = _checked_in_players(tournament)
    n = len(players)
    if n < 8 or (n & (n - 1)) != 0:
        raise ValidationError({
            'detail': (
                f'3-game guarantee needs an exact power of two players, at least 8 '
                f'(8, 16, or 32) — you have {n} registered.'
            ),
        })

    k = n.bit_length() - 1
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=k, format=Bracket.Format.GUARANTEE3)
    core = _build_double_elim_core(bracket, tournament, players)

    # The players who lose their very first losers-bracket match have now lost twice
    # (WB round 1, then LB round 1) — give them one bonus "guarantee" match against each
    # other instead of eliminating them outright. It doesn't feed anywhere further.
    _pair_losers(bracket, tournament, 1, core['lb_seed_matches'], side=Match.Side.GUARANTEE)

    _attach_grand_final(bracket, tournament, core['wb_final'], core['lb_final'])
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


def generate_round_robin_bracket(tournament):
    players = _checked_in_players(tournament)
    if len(players) < 2:
        raise ValidationError({'detail': 'At least 2 registered players are required for round robin.'})

    rounds = _round_robin_rounds(players)
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=len(rounds), format=Bracket.Format.ROUND_ROBIN)
    for round_number, pairs in enumerate(rounds, start=1):
        for position, (p1, p2) in enumerate(pairs):
            Match.objects.create(
                bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
                round_number=round_number, position=position, player1=p1, player2=p2, status=Match.Status.READY,
            )
    return bracket


def _have_played(tournament, p1, p2):
    return Match.objects.filter(tournament=tournament, player1=p1, player2=p2).exists() or \
        Match.objects.filter(tournament=tournament, player1=p2, player2=p1).exists()


def _create_swiss_round(bracket, tournament, round_number, ranked_players):
    """Pair `ranked_players` adjacently (1v2, 3v4, ...). From round 2 on, if adjacent
    players already met, swap in the next player down who hasn't — if nobody
    qualifies, the rematch is allowed rather than the algorithm getting stuck. An odd
    player out gets an automatic bye win for the round."""
    pool = list(ranked_players)
    pairs = []
    while len(pool) >= 2:
        p1 = pool.pop(0)
        idx = 0
        if round_number > 1 and _have_played(tournament, p1, pool[0]):
            for j in range(1, len(pool)):
                if not _have_played(tournament, p1, pool[j]):
                    idx = j
                    break
        p2 = pool.pop(idx)
        pairs.append((p1, p2))

    for position, (p1, p2) in enumerate(pairs):
        Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
            round_number=round_number, position=position, player1=p1, player2=p2, status=Match.Status.READY,
        )

    if pool:
        bye_player = pool[0]
        bye_match = Match.objects.create(
            bracket=bracket, tournament=tournament, bracket_side=Match.Side.WINNERS,
            round_number=round_number, position=len(pairs), player1=bye_player, status=Match.Status.READY,
        )
        complete_match(bye_match, bye_player)


def generate_swiss_bracket(tournament):
    players = _checked_in_players(tournament)
    n = len(players)
    if n < 2:
        raise ValidationError({'detail': 'At least 2 registered players are required for a Swiss bracket.'})

    total_rounds = max(1, math.ceil(math.log2(n)))
    bracket = Bracket.objects.create(tournament=tournament, total_rounds=total_rounds, format=Bracket.Format.SWISS)
    _create_swiss_round(bracket, tournament, 1, players)
    return bracket


def generate_next_swiss_round(bracket):
    if bracket.format != Bracket.Format.SWISS:
        raise ValidationError({'detail': 'This bracket is not a Swiss bracket.'})

    tournament = bracket.tournament
    matches = list(Match.objects.filter(bracket=bracket))
    current_round = max(m.round_number for m in matches)
    if any(m.status != Match.Status.COMPLETED for m in matches if m.round_number == current_round):
        raise ValidationError({'detail': f'Round {current_round} is not finished yet.'})
    if current_round >= bracket.total_rounds:
        raise ValidationError({'detail': 'This Swiss bracket has already reached its final round.'})

    ranked_players = [row['player'] for row in standings(tournament)]
    _create_swiss_round(bracket, tournament, current_round + 1, ranked_players)
    return bracket


def generate_group_playoff_bracket(tournament, num_groups=None):
    players = _checked_in_players(tournament)
    n = len(players)
    if num_groups is None:
        num_groups = max(2, round(n / 4)) if n else 2
    num_groups = max(2, int(num_groups))
    if n < 2 * num_groups:
        raise ValidationError({
            'detail': f'Need at least {2 * num_groups} registered players for {num_groups} groups — you have {n}.',
        })

    labels = [chr(ord('A') + i) for i in range(num_groups)]
    groups = {label: [] for label in labels}
    for i, p in enumerate(players):
        groups[labels[i % num_groups]].append(p)

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


def generate_group_playoff_bracket_phase2(bracket):
    if bracket.format != Bracket.Format.GROUP_PLAYOFF:
        raise ValidationError({'detail': 'This bracket is not a group + playoff bracket.'})

    tournament = bracket.tournament
    group_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP)
    if group_matches.filter(status__in=[Match.Status.PENDING, Match.Status.READY]).exists():
        raise ValidationError({'detail': 'The group stage is not finished yet.'})
    if Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS).exists():
        raise ValidationError({'detail': 'The playoff bracket has already been generated.'})

    all_players = _checked_in_players(tournament)
    labels = sorted(set(group_matches.values_list('group_label', flat=True)))

    qualifiers = []
    for label in labels:
        ids_in_group = set()
        for m in group_matches.filter(group_label=label):
            ids_in_group.add(m.player1_id)
            ids_in_group.add(m.player2_id)
        group_players = [p for p in all_players if p.pk in ids_in_group]
        group_standings = standings(tournament, group_players)
        qualifiers.append(group_standings[0]['player'])

    _build_single_elim(bracket, tournament, qualifiers, bracket_side=Match.Side.WINNERS)
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
        grand_final = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL).first()
        return grand_final.winner if grand_final and grand_final.status == Match.Status.COMPLETED else None

    if bracket.format == Bracket.Format.ROUND_ROBIN:
        matches = Match.objects.filter(bracket=bracket)
        if not matches.exists() or matches.exclude(status=Match.Status.COMPLETED).exists():
            return None
        ranked = standings(tournament)
        return ranked[0]['player'] if ranked else None

    if bracket.format == Bracket.Format.SWISS:
        final_round = Match.objects.filter(bracket=bracket, round_number=bracket.total_rounds)
        if not final_round.exists() or final_round.exclude(status=Match.Status.COMPLETED).exists():
            return None
        ranked = standings(tournament)
        return ranked[0]['player'] if ranked else None

    return None


def finalize_tournament_champion(tournament):
    """Persist the tournament's champion (idempotent — a champion, once set, is
    never recomputed or overwritten) and send the win email the first time it's
    decided. Call this after every match result submission; it's a no-op for
    every call that doesn't happen to be the tournament-deciding one."""
    if tournament.champion_id:
        return tournament.champion

    champion = get_tournament_champion(tournament)
    if champion is None:
        return None

    tournament.champion = champion
    tournament.champion_declared_at = timezone.now()
    tournament.save(update_fields=['champion', 'champion_declared_at'])

    from tourny_regist.emails import send_tournament_win_email
    send_tournament_win_email(tournament, champion)
    return champion
