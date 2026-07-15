from brackets.models import Bracket, Match


def _next_power_of_two(n):
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def complete_match(match, winner, score=''):
    match.winner = winner
    match.score = score
    match.status = Match.Status.COMPLETED
    match.save(update_fields=['winner', 'score', 'status'])

    next_match = match.next_match
    if next_match is None:
        return

    if match.next_match_slot == 1:
        next_match.player1 = winner
    else:
        next_match.player2 = winner
    if next_match.player1_id and next_match.player2_id:
        next_match.status = Match.Status.READY
    next_match.save()


def generate_bracket(tournament):
    players = [r.player for r in tournament.registrations.order_by('registered_at')]
    bracket_size = _next_power_of_two(len(players))
    total_rounds = bracket_size.bit_length() - 1
    padded = players + [None] * (bracket_size - len(players))

    bracket = Bracket.objects.create(tournament=tournament, total_rounds=total_rounds)

    round_matches = []
    for i in range(bracket_size // 2):
        p1, p2 = padded[2 * i], padded[2 * i + 1]
        initial_status = Match.Status.READY if (p1 and p2) else Match.Status.PENDING
        match = Match.objects.create(
            bracket=bracket, tournament=tournament, round_number=1, position=i,
            player1=p1, player2=p2, status=initial_status,
        )
        round_matches.append(match)

    current_round_matches = round_matches
    for round_number in range(2, total_rounds + 1):
        next_round_matches = []
        for i in range(len(current_round_matches) // 2):
            match = Match.objects.create(bracket=bracket, tournament=tournament, round_number=round_number, position=i)
            next_round_matches.append(match)
            for slot, prev in ((1, current_round_matches[2 * i]), (2, current_round_matches[2 * i + 1])):
                prev.next_match = match
                prev.next_match_slot = slot
                prev.save(update_fields=['next_match', 'next_match_slot'])
        current_round_matches = next_round_matches

    for match in round_matches:
        if match.player1_id and not match.player2_id:
            complete_match(match, match.player1)
        elif match.player2_id and not match.player1_id:
            complete_match(match, match.player2)

    return bracket
