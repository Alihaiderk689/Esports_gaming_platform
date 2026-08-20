import ast
import inspect
import random
import threading
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from brackets import services
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APITestCase

from brackets.models import Bracket, Match
from brackets.services import (
    GUARANTEED_GAMES,
    _min_real_games_before,
    _next_power_of_two,
    _real_opponents,
    _topological_matches,
    bye_matches,
    format_standings,
    group_stage_standings,
    complete_match,
    finalize_tournament_champion,
    generate_bracket,
    generate_double_elimination_bracket,
    generate_group_playoff_bracket,
    generate_group_playoff_bracket_phase2,
    generate_next_swiss_round,
    generate_round_robin_bracket,
    generate_swiss_bracket,
    generate_three_game_guarantee_bracket,
    standings,
    disqualify_player_from_bracket,
    forfeit_match,
    override_match_result,
)
from core.models import AdminReviewRequest
from games.models import Game
from organizer.models import Organizer
from tourny_regist.lifecycle import disqualify_registration
from tourny_regist.models import Registration, Tournament

User = get_user_model()


class BracketApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        self.organizer_user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Acme Esports')
        self.other_organizer_user = User.objects.create_user(email='other-organizer@example.com', password='StrongPass123')
        self.other_organizer = Organizer.objects.create(user=self.other_organizer_user, company_name='Other Co')
        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)
        self.players = [
            User.objects.create_user(email=f'player{i}@example.com', password='StrongPass123') for i in range(4)
        ]
        self.tournament = Tournament.objects.create(
            name='Winter Cup', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.organizer_user)

    def _register(self, tournament, players):
        for player in players:
            Registration.objects.create(tournament=tournament, player=player, checked_in=True)

    def test_generate_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_forbidden_for_player(self):
        self._register(self.tournament, self.players)
        self.client.force_authenticate(user=self.players[0])
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_forbidden_for_other_organizer(self):
        self._register(self.tournament, self.players)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_requires_two_players(self):
        self._register(self.tournament, self.players[:1])
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_twice_rejected(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_closes_registration(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.tournament.refresh_from_db()
        self.assertFalse(self.tournament.is_registration_open)

    def test_generate_power_of_two_bracket(self):
        self._register(self.tournament, self.players)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['total_rounds'], 2)
        self.assertEqual(len(resp.data['rounds']), 2)
        self.assertEqual(len(resp.data['rounds'][0]['matches']), 2)
        self.assertEqual(len(resp.data['rounds'][1]['matches']), 1)
        for match in resp.data['rounds'][0]['matches']:
            self.assertEqual(match['status'], 'ready')
        self.assertEqual(resp.data['rounds'][1]['matches'][0]['status'], 'pending')

    def test_generate_with_bye(self):
        self._register(self.tournament, self.players[:3])
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        round1 = resp.data['rounds'][0]['matches']
        self.assertEqual(len(round1), 2)
        completed = [m for m in round1 if m['status'] == 'completed']
        ready = [m for m in round1 if m['status'] == 'ready']
        self.assertEqual(len(completed), 1)
        self.assertEqual(len(ready), 1)
        self.assertIsNotNone(completed[0]['winner'])

        round2 = resp.data['rounds'][1]['matches']
        self.assertEqual(len(round2), 1)
        self.assertTrue(round2[0]['player1'] is not None or round2[0]['player2'] is not None)
        self.assertEqual(round2[0]['status'], 'pending')

    def test_generate_with_multiple_byes_seeds_top_players_and_leaves_no_empty_match(self):
        # 5 players -> bracket_size 8 -> 3 byes. Regression test: the previous
        # implementation padded byes at the end of the list rather than seeding them
        # properly, which could produce a match with *both* slots empty when more
        # than one bye was needed.
        extra_players = [
            User.objects.create_user(email=f'extra-player{i}@example.com', password='StrongPass123')
            for i in range(2)
        ]
        five_players = self.players[:3] + extra_players
        self._register(self.tournament, five_players)

        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        round1 = resp.data['rounds'][0]['matches']
        self.assertEqual(len(round1), 4)
        for match in round1:
            self.assertTrue(match['player1'] is not None or match['player2'] is not None)

        completed = [m for m in round1 if m['status'] == 'completed']
        ready = [m for m in round1 if m['status'] == 'ready']
        self.assertEqual(len(completed), 3)
        self.assertEqual(len(ready), 1)

        # The 3 byes should go to the top 3 seeds (first 3 registered) — the 2
        # latest registrants should be the ones actually playing a round-1 match.
        top_seed_ids = {p.pk for p in five_players[:3]}
        bye_winner_ids = {m['winner'] for m in completed}
        self.assertEqual(bye_winner_ids, top_seed_ids)

    def test_get_bracket_before_generation_404(self):
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_bracket_any_authenticated_user(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.client.force_authenticate(user=self.players[0])
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_get_tournament_matches(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        self.client.force_authenticate(user=self.players[0])
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/matches/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        self.assertEqual(len(results), 3)

    def test_get_match_detail(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        match = Match.objects.filter(round_number=1).first()
        self.client.force_authenticate(user=self.players[0])
        resp = self.client.get(f'/api/matches/{match.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['round_number'], 1)

    def test_full_bracket_progression(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        round1_matches = list(Match.objects.filter(tournament=self.tournament, round_number=1).order_by('position'))

        winners = []
        for match in round1_matches:
            resp = self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            winners.append(match.player1_id)

        final_match = Match.objects.get(tournament=self.tournament, round_number=2)
        final_match.refresh_from_db()
        self.assertEqual(final_match.status, Match.Status.READY)
        self.assertEqual({final_match.player1_id, final_match.player2_id}, set(winners))

        resp = self.client.patch(
            f'/api/matches/{final_match.pk}/result/', {'winner': final_match.player1_id, 'score': '3-1'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'completed')
        self.assertEqual(resp.data['score'], '3-1')

    def test_result_forbidden_for_player(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        match = Match.objects.filter(round_number=1).first()
        self.client.force_authenticate(user=self.players[0])
        resp = self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_result_allowed_for_admin(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        match = Match.objects.filter(round_number=1).first()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_result_on_not_ready_match_rejected(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        final_match = Match.objects.get(tournament=self.tournament, round_number=2)
        resp = self.client.patch(f'/api/matches/{final_match.pk}/result/', {'winner': self.players[0].pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_invalid_winner_rejected(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        match = Match.objects.filter(round_number=1).first()
        outsider = User.objects.create_user(email='outsider@example.com', password='StrongPass123')
        resp = self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': outsider.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_already_completed_rejected(self):
        self._register(self.tournament, self.players)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/brackets/')
        match = Match.objects.filter(round_number=1).first()
        self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
        resp = self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class BracketTestMixin:
    """Shared fixtures/helpers. A plain mixin rather than a base TestCase so the
    classes below don't inherit — and therefore re-run — each other's tests."""

    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        self.organizer_user = User.objects.create_user(email='geo@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Geo Co')
        self._counter = 0

    def _tournament(self, n):
        self._counter += 1
        players = [
            User.objects.create_user(email=f'gp{self._counter}-{i}@example.com', password='StrongPass123')
            for i in range(n)
        ]
        tournament = Tournament.objects.create(
            name=f'GT{self._counter}', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
        )
        for p in players:
            Registration.objects.create(tournament=tournament, player=p, checked_in=True)
        return tournament, players

    def _play_all(self, tournament, bracket, pick=None):
        """Complete every READY match until none remain, calling
        finalize_tournament_champion after each one exactly like the real
        result-submission view does. `pick(match)` chooses the winner (default:
        player1). Returns every match actually completed this way (i.e. every *real*,
        two-player match — byes are already completed during generation and never show
        up as READY)."""
        pick = pick or (lambda m: m.player1)
        played = []
        while True:
            ready = list(Match.objects.filter(bracket=bracket, status=Match.Status.READY))
            if not ready:
                break
            for m in ready:
                m.refresh_from_db()
                if m.status != Match.Status.READY:
                    continue
                complete_match(m, pick(m))
                played.append(m)
                finalize_tournament_champion(tournament)
        return played

    @staticmethod
    def _real_games_per_player(played):
        counts = {}
        for m in played:
            if m.player1_id and m.player2_id:
                counts[m.player1_id] = counts.get(m.player1_id, 0) + 1
                counts[m.player2_id] = counts.get(m.player2_id, 0) + 1
        return counts


class GeneralizedBracketServiceTests(BracketTestMixin, APITestCase):
    """Service-layer tests for arbitrary (non-power-of-two) participant counts across
    every format. These call the `generate_*`/`services` functions directly rather than
    through the API, and assert on the actual Match graph — not just HTTP shapes —
    since the whole point of this suite is verifying the generated bracket is
    structurally sound (correct winner/loser propagation, no fabricated players, no
    player eliminated after only one loss in double elimination, etc.), not merely that
    a request returns 201."""

    # ---- single elimination: arbitrary counts, bye placement ----

    def test_single_elim_bye_counts_across_arbitrary_n(self):
        cases = [3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17]
        for n in cases:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_bracket(tournament)

                bracket_size = _next_power_of_two(n)
                expected_byes = bracket_size - n
                round1 = Match.objects.filter(tournament=tournament, bracket_side=Match.Side.WINNERS, round_number=1)
                self.assertEqual(round1.count(), bracket_size // 2)
                self.assertEqual(round1.filter(status=Match.Status.COMPLETED).count(), expected_byes)

                # every checked-in player appears exactly once in the initial bracket
                seeded = []
                for m in round1:
                    self.assertTrue(m.player1_id or m.player2_id, f'n={n}: empty match {m.pk}')
                    self.assertNotEqual(m.player1_id, m.player2_id, f'n={n}: duplicate player in match {m.pk}')
                    seeded.extend(pid for pid in (m.player1_id, m.player2_id) if pid)
                self.assertEqual(sorted(seeded), sorted(p.pk for p in players), f'n={n}: player set mismatch')

                # a bye advances its player and never routes a loser anywhere
                for m in round1.filter(status=Match.Status.COMPLETED):
                    self.assertTrue(bool(m.player1_id) != bool(m.player2_id), f'n={n}: 2-player match auto-completed')
                    self.assertEqual(m.winner_id, m.player1_id or m.player2_id)
                    self.assertIsNone(m.loser_next_match_id, f'n={n}: bye {m.pk} routes a loser')

                # exactly one final (the root), and finishing it crowns the champion
                roots = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS, next_match__isnull=True)
                self.assertEqual(roots.count(), 1, f'n={n}: expected exactly one root match')
                played = self._play_all(tournament, bracket)
                for m in played:
                    self.assertTrue(m.player1_id and m.player2_id, f'n={n}: played a match with a missing player')
                tournament.refresh_from_db()
                self.assertEqual(tournament.champion_id, roots.first().winner_id)
                # a single-elimination field of n needs exactly n-1 real matches
                self.assertEqual(len(played), n - 1, f'n={n}: expected {n - 1} real matches, got {len(played)}')

    # ---- double elimination: arbitrary counts, full structural verification ----

    def test_double_elimination_arbitrary_counts(self):
        for n in range(4, 17):
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_double_elimination_bracket(tournament)
                self._assert_double_elim_structure(tournament, bracket, players, n)

    def test_three_game_guarantee_arbitrary_counts(self):
        for n in range(8, 17):
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_three_game_guarantee_bracket(tournament)
                self._assert_double_elim_structure(tournament, bracket, players, n)

                guarantee_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GUARANTEE)
                for m in guarantee_matches:
                    m.refresh_from_db()
                    self.assertIsNotNone(m.player1_id, f'n={n}: guarantee match {m.pk} missing player1')
                    self.assertIsNotNone(m.player2_id, f'n={n}: guarantee match {m.pk} missing player2')
                    self.assertNotEqual(m.player1_id, m.player2_id)
                    self.assertEqual(m.status, Match.Status.COMPLETED)
                    self.assertIsNone(m.next_match_id, f'n={n}: guarantee match {m.pk} feeds back into the main tree')

    def _assert_double_elim_structure(self, tournament, bracket, players, n):
        all_matches = list(Match.objects.filter(bracket=bracket))
        for m in all_matches:
            if m.player1_id and m.player2_id:
                self.assertNotEqual(m.player1_id, m.player2_id, f'n={n}: match {m.pk} has the same player twice')

        # Every winners-bracket round-1 bye never produces a loser anywhere, now or later.
        wb_round1_byes = Match.objects.filter(
            bracket=bracket, bracket_side=Match.Side.WINNERS, round_number=1,
        ).filter(status=Match.Status.COMPLETED)
        for bye in wb_round1_byes:
            self.assertTrue(bool(bye.player1_id) != bool(bye.player2_id), f'n={n}: bye match {bye.pk} has 2 players')
            self.assertIsNone(bye.loser_next_match_id, f'n={n}: bye match {bye.pk} has a loser_next_match')

        played = self._play_all(tournament, bracket)
        for m in played:
            self.assertIsNotNone(m.player1_id)
            self.assertIsNotNone(m.player2_id)
            self.assertNotEqual(m.player1_id, m.player2_id)

        tournament.refresh_from_db()
        self.assertIsNotNone(tournament.champion, f'n={n}: no champion decided')

        # 3-game-guarantee's bonus matches are dead-end consolation games — the player
        # who loses one is already eliminated (they lost it after their 2nd real loss),
        # so they're excluded from the elimination-loss accounting below.
        elimination_played = [m for m in played if m.bracket_side != Match.Side.GUARANTEE]

        losses = {}
        for m in elimination_played:
            loser_id = m.player2_id if m.winner_id == m.player1_id else m.player1_id
            losses[loser_id] = losses.get(loser_id, 0) + 1

        champion_id = tournament.champion_id
        for p in players:
            loss_count = losses.get(p.pk, 0)
            if p.pk == champion_id:
                self.assertLessEqual(loss_count, 1, f'n={n}: champion has {loss_count} losses')
            else:
                self.assertEqual(loss_count, 2, f'n={n}: player {p.pk} eliminated after {loss_count} losses, not 2')

        # 1 loss per non-champion in the winners bracket + 1 loss per non-WB-champion in
        # the losers bracket/grand-final = exactly 2*(n-1) real matches total.
        self.assertEqual(
            len(elimination_played), 2 * (n - 1),
            f'n={n}: expected {2 * (n - 1)} elimination matches, got {len(elimination_played)}',
        )

    def test_double_elimination_below_minimum_rejected(self):
        tournament, players = self._tournament(3)
        with self.assertRaises(Exception):
            generate_double_elimination_bracket(tournament)

    def test_three_game_guarantee_below_minimum_rejected(self):
        tournament, players = self._tournament(6)
        with self.assertRaises(Exception):
            generate_three_game_guarantee_bracket(tournament)

    # ---- round robin: odd/arbitrary counts ----

    def test_round_robin_arbitrary_counts(self):
        for n in [3, 5, 6, 7]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_round_robin_bracket(tournament)
                matches = list(Match.objects.filter(bracket=bracket))
                self.assertEqual(len(matches), n * (n - 1) // 2)

                appearances = {p.pk: 0 for p in players}
                seen_pairs = set()
                for m in matches:
                    # no phantom bye is ever materialised as a real match
                    self.assertIsNotNone(m.player1_id, f'n={n}: match {m.pk} has no player1')
                    self.assertIsNotNone(m.player2_id, f'n={n}: bye materialised as a real match')
                    # nobody plays themselves
                    self.assertNotEqual(m.player1_id, m.player2_id)
                    # every pair meets exactly once
                    pair = frozenset((m.player1_id, m.player2_id))
                    self.assertNotIn(pair, seen_pairs, f'n={n}: pair {pair} scheduled twice')
                    seen_pairs.add(pair)
                    appearances[m.player1_id] += 1
                    appearances[m.player2_id] += 1

                # nobody plays twice in the same round
                by_round = {}
                for m in matches:
                    players_this_round = by_round.setdefault(m.round_number, set())
                    for pid in (m.player1_id, m.player2_id):
                        self.assertNotIn(pid, players_this_round, f'n={n}: player {pid} twice in round {m.round_number}')
                        players_this_round.add(pid)
                for p in players:
                    self.assertEqual(appearances[p.pk], n - 1, f'n={n}: player {p.pk} plays {appearances[p.pk]} games')

    # ---- swiss: arbitrary/odd counts, bye fairness, played-vs-bye stat separation ----

    def test_swiss_arbitrary_counts_bye_fairness_and_stats(self):
        for n in [3, 5, 6, 7, 9, 10]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_swiss_bracket(tournament)

                bye_recipients = []
                seen_pairs = set()
                while True:
                    current_round = max(m.round_number for m in Match.objects.filter(bracket=bracket))
                    matches = list(Match.objects.filter(bracket=bracket, round_number=current_round))
                    byes_this_round = [m for m in matches if m.player2_id is None]
                    self.assertLessEqual(len(byes_this_round), 1, f'n={n}: more than one bye in a single round')
                    if byes_this_round:
                        bye_recipients.append(byes_this_round[0].player1_id)

                    # within a round: nobody plays themselves, nobody appears twice
                    playing_this_round = set()
                    for m in matches:
                        self.assertNotEqual(m.player1_id, m.player2_id, f'n={n}: self-match {m.pk}')
                        for pid in (m.player1_id, m.player2_id):
                            if pid is None:
                                continue
                            self.assertNotIn(pid, playing_this_round, f'n={n}: player {pid} twice in one round')
                            playing_this_round.add(pid)
                        # every player in the round is a real checked-in participant
                        if m.player2_id is not None:
                            pair = frozenset((m.player1_id, m.player2_id))
                            # rematch avoidance: with n > rounds there is always a
                            # rematch-free pairing available, so none should occur
                            self.assertNotIn(pair, seen_pairs, f'n={n}: avoidable rematch {pair} in round {current_round}')
                            seen_pairs.add(pair)

                    for m in matches:
                        if m.status == Match.Status.READY:
                            complete_match(m, m.player1)

                    if current_round >= bracket.total_rounds:
                        break
                    generate_next_swiss_round(bracket)

                if n % 2 == 1 and bye_recipients:
                    # nobody should receive a second bye while another player still has zero
                    counts = {p.pk: 0 for p in players}
                    for pid in bye_recipients:
                        counts[pid] += 1
                    self.assertLessEqual(
                        max(counts.values()) - min(counts.values()), 1, f'n={n}: bye counts not balanced: {counts}',
                    )

                # a bye must count as a win but never as a "played" game
                final_standings = standings(tournament)
                completed_byes = Match.objects.filter(
                    bracket=bracket, status=Match.Status.COMPLETED, player2__isnull=True,
                )
                bye_counts_final = {}
                for m in completed_byes:
                    bye_counts_final[m.player1_id] = bye_counts_final.get(m.player1_id, 0) + 1
                real_match_counts = {p.pk: 0 for p in players}
                for m in Match.objects.filter(bracket=bracket, status=Match.Status.COMPLETED, player2__isnull=False):
                    real_match_counts[m.player1_id] += 1
                    real_match_counts[m.player2_id] += 1
                for row in final_standings:
                    self.assertEqual(
                        row['played'], real_match_counts[row['player'].pk],
                        f"n={n}: standings 'played' includes a bye for player {row['player'].pk}",
                    )

    # ---- group + playoff: snake distribution, configurable qualifiers ----

    def test_group_playoff_snake_distribution(self):
        tournament, players = self._tournament(9)
        bracket = generate_group_playoff_bracket(tournament, num_groups=3)
        group_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP)
        ids_by_group = {}
        for m in group_matches:
            ids_by_group.setdefault(m.group_label, set()).update([m.player1_id, m.player2_id])

        expected_by_group = {'A': {0, 5, 6}, 'B': {1, 4, 7}, 'C': {2, 3, 8}}
        for label, expected_indices in expected_by_group.items():
            expected_ids = {players[i].pk for i in expected_indices}
            self.assertEqual(ids_by_group[label], expected_ids, f'group {label} does not match snake distribution')

    def test_group_playoff_snake_distribution_16_players_4_groups(self):
        # The textbook case: 16 seeds into 4 groups should serpentine
        # A,B,C,D / D,C,B,A / A,B,C,D / D,C,B,A so each group draws one player from
        # every strength band instead of group A hoarding the top seeds.
        tournament, players = self._tournament(16)
        bracket = generate_group_playoff_bracket(tournament, num_groups=4)
        group_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP)
        ids_by_group = {}
        for m in group_matches:
            ids_by_group.setdefault(m.group_label, set()).update([m.player1_id, m.player2_id])

        # seeds are 1-indexed in the comment, players[] is 0-indexed
        expected_seeds = {'A': [1, 8, 9, 16], 'B': [2, 7, 10, 15], 'C': [3, 6, 11, 14], 'D': [4, 5, 12, 13]}
        for label, seeds in expected_seeds.items():
            expected_ids = {players[s - 1].pk for s in seeds}
            self.assertEqual(ids_by_group[label], expected_ids, f'group {label}: expected seeds {seeds}')

    def test_standings_separates_wins_losses_played_and_byes(self):
        tournament, players = self._tournament(5)
        bracket = generate_swiss_bracket(tournament)
        round1 = list(Match.objects.filter(bracket=bracket, round_number=1))
        bye_match = next(m for m in round1 if m.player2_id is None)
        for m in round1:
            if m.status == Match.Status.READY:
                complete_match(m, m.player1)

        rows = {row['player'].pk: row for row in standings(tournament)}

        bye_row = rows[bye_match.player1_id]
        self.assertEqual(bye_row['byes'], 1)
        self.assertEqual(bye_row['played'], 0, 'a bye is not a game against an opponent')
        self.assertEqual(bye_row['losses'], 0, 'a bye can never be a loss')
        self.assertEqual(bye_row['wins'], 1, 'a bye still advances the player, so it scores as a win')

        for m in round1:
            if m.player2_id is None:
                continue
            winner_row, loser_row = rows[m.player1_id], rows[m.player2_id]
            self.assertEqual((winner_row['wins'], winner_row['losses'], winner_row['played'], winner_row['byes']), (1, 0, 1, 0))
            self.assertEqual((loser_row['wins'], loser_row['losses'], loser_row['played'], loser_row['byes']), (0, 1, 1, 0))

    def test_group_playoff_uneven_counts_and_configurable_qualifiers(self):
        tournament, players = self._tournament(10)
        bracket = generate_group_playoff_bracket(tournament, num_groups=3)
        group_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP)

        group_sizes = {}
        for m in group_matches:
            group_sizes.setdefault(m.group_label, set()).update([m.player1_id, m.player2_id])
        sizes = sorted(len(v) for v in group_sizes.values())
        self.assertLessEqual(sizes[-1] - sizes[0], 1, 'group sizes should be balanced within 1 of each other')

        for m in group_matches:
            m.status = Match.Status.COMPLETED
            m.winner_id = m.player1_id
            m.save(update_fields=['status', 'winner'])

        generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=2)
        playoff_matches = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS)
        playoff_players = set()
        for m in playoff_matches:
            playoff_players.update(pid for pid in (m.player1_id, m.player2_id) if pid)
        self.assertEqual(len(playoff_players), len(group_sizes) * 2)


class BracketRefinementTests(BracketTestMixin, APITestCase):
    """Second-pass refinements: grand-final reset, a 3-game guarantee that actually
    holds on every result path, score-group Swiss pairing with Buchholz tiebreaks,
    playoff seeding that avoids same-group rematches, and determinism."""

    # ---- grand final reset ----

    def test_wb_finalist_winning_grand_final_ends_tournament(self):
        tournament, players = self._tournament(8)
        bracket = generate_double_elimination_bracket(tournament)
        self._play_all(tournament, bracket)  # player1 wins everything; slot 1 is the WB finalist

        grand_finals = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL)
        self.assertEqual(grand_finals.count(), 1, 'no reset should be created when the WB finalist wins')
        tournament.refresh_from_db()
        self.assertEqual(tournament.champion_id, grand_finals.first().winner_id)

    def test_lb_finalist_winning_grand_final_forces_a_reset(self):
        tournament, players = self._tournament(8)
        bracket = generate_double_elimination_bracket(tournament)

        # Play everything up to (but not including) the grand final.
        while True:
            ready = list(Match.objects.filter(bracket=bracket, status=Match.Status.READY)
                         .exclude(bracket_side=Match.Side.GRAND_FINAL))
            if not ready:
                break
            for m in ready:
                m.refresh_from_db()
                if m.status == Match.Status.READY:
                    complete_match(m, m.player1)
                    finalize_tournament_champion(tournament)

        gf = Match.objects.get(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL, round_number=1)
        self.assertEqual(gf.status, Match.Status.READY)

        # The losers-bracket finalist (slot 2) wins: both now have one loss.
        complete_match(gf, gf.player2)
        finalize_tournament_champion(tournament)

        tournament.refresh_from_db()
        self.assertIsNone(tournament.champion, 'winning GF1 from the losers bracket must not crown a champion')

        reset = Match.objects.get(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL, round_number=2)
        self.assertEqual(reset.status, Match.Status.READY)
        self.assertEqual({reset.player1_id, reset.player2_id}, {gf.player1_id, gf.player2_id})

        # Whoever wins the reset is champion — check the WB finalist can still take it.
        complete_match(reset, reset.player1)
        finalize_tournament_champion(tournament)
        tournament.refresh_from_db()
        self.assertEqual(tournament.champion_id, gf.player1_id)

    def test_lb_finalist_can_win_the_reset_and_become_champion(self):
        tournament, players = self._tournament(8)
        bracket = generate_double_elimination_bracket(tournament)
        self._play_all(
            tournament, bracket,
            pick=lambda m: m.player2 if m.bracket_side == Match.Side.GRAND_FINAL else m.player1,
        )
        tournament.refresh_from_db()
        reset = Match.objects.get(bracket=bracket, bracket_side=Match.Side.GRAND_FINAL, round_number=2)
        self.assertEqual(tournament.champion_id, reset.winner_id)
        self.assertEqual(tournament.champion_id, reset.player2_id)

    def test_double_elim_champion_never_has_two_losses(self):
        for n in [4, 5, 6, 7, 8, 9, 16]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_double_elimination_bracket(tournament)
                played = self._play_all(
                    tournament, bracket,
                    pick=lambda m: m.player2 if m.bracket_side == Match.Side.GRAND_FINAL else m.player1,
                )
                tournament.refresh_from_db()
                losses = {}
                for m in played:
                    loser = m.player2_id if m.winner_id == m.player1_id else m.player1_id
                    losses[loser] = losses.get(loser, 0) + 1
                self.assertLessEqual(losses.get(tournament.champion_id, 0), 1,
                                     f'n={n}: champion finished with 2 losses')

    # ---- 3-game guarantee, verified across many result paths ----

    def test_three_game_guarantee_holds_on_every_simulated_path(self):
        for n in [8, 9, 10, 11, 12, 13, 16]:
            for trial in range(6):
                with self.subTest(n=n, trial=trial):
                    tournament, players = self._tournament(n)
                    bracket = generate_three_game_guarantee_bracket(tournament)
                    rng = random.Random(f'{n}-{trial}')
                    played = self._play_all(
                        tournament, bracket,
                        pick=lambda m: rng.choice([m.player1, m.player2]),
                    )
                    counts = self._real_games_per_player(played)
                    short = {seed + 1: counts.get(p.pk, 0)
                             for seed, p in enumerate(players) if counts.get(p.pk, 0) < 3}
                    self.assertEqual(short, {}, f'n={n} trial={trial}: players with fewer than 3 real games: {short}')

    def test_guarantee_matches_are_dead_ends_with_real_players(self):
        tournament, players = self._tournament(11)
        bracket = generate_three_game_guarantee_bracket(tournament)
        self._play_all(tournament, bracket)
        guarantee = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GUARANTEE)
        self.assertTrue(guarantee.exists())
        for m in guarantee:
            self.assertIsNotNone(m.player1_id)
            self.assertIsNotNone(m.player2_id)
            self.assertNotEqual(m.player1_id, m.player2_id)
            self.assertIsNone(m.next_match_id)
            self.assertIsNone(m.loser_next_match_id)

    # ---- swiss: score groups, buchholz, byes ----

    def test_swiss_pairs_within_score_groups(self):
        tournament, players = self._tournament(8)
        bracket = generate_swiss_bracket(tournament)

        for m in Match.objects.filter(bracket=bracket, round_number=1):
            complete_match(m, m.player1)
        generate_next_swiss_round(bracket)

        wins = {row['player'].pk: row['wins'] for row in standings(tournament)}
        for m in Match.objects.filter(bracket=bracket, round_number=2):
            if m.player2_id is None:
                continue
            self.assertEqual(
                wins[m.player1_id], wins[m.player2_id],
                'round 2 of an 8-player Swiss should pair 1-0 with 1-0 and 0-1 with 0-1',
            )

    def test_swiss_round_one_uses_dutch_split(self):
        # 8 players, all on zero: one score group, so seed 1 should meet seed 5.
        tournament, players = self._tournament(8)
        bracket = generate_swiss_bracket(tournament)
        pairs = {
            frozenset((m.player1_id, m.player2_id))
            for m in Match.objects.filter(bracket=bracket, round_number=1)
        }
        expected = {frozenset((players[i].pk, players[i + 4].pk)) for i in range(4)}
        self.assertEqual(pairs, expected)

    def test_median_buchholz_discards_extremes_and_ignores_byes(self):
        tournament, players = self._tournament(5)
        bracket = generate_swiss_bracket(tournament)
        while True:
            current = max(m.round_number for m in Match.objects.filter(bracket=bracket))
            for m in Match.objects.filter(bracket=bracket, round_number=current, status=Match.Status.READY):
                complete_match(m, m.player1)
            if current >= bracket.total_rounds:
                break
            generate_next_swiss_round(bracket)

        rows = standings(tournament, tiebreakers=['median_buchholz', 'buchholz'])
        wins = {row['player'].pk: row['wins'] for row in rows}
        opponents = _real_opponents(tournament, [p.pk for p in players])

        for row in rows:
            pid = row['player'].pk
            scores = sorted(wins[o] for o in opponents[pid])
            self.assertEqual(row['tiebreaks']['buchholz'], sum(scores))
            trimmed = scores[1:-1] if len(scores) >= 3 else scores
            self.assertEqual(row['tiebreaks']['median_buchholz'], sum(trimmed))
            # a bye is never an opponent, so it can never appear in the opponent list
            self.assertEqual(len(opponents[pid]), row['played'])

    def test_swiss_no_rematches_across_full_events(self):
        for n in [5, 6, 7, 8, 9, 10, 16]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_swiss_bracket(tournament)
                seen = set()
                while True:
                    current = max(m.round_number for m in Match.objects.filter(bracket=bracket))
                    for m in Match.objects.filter(bracket=bracket, round_number=current):
                        if m.player2_id is not None:
                            pair = frozenset((m.player1_id, m.player2_id))
                            self.assertNotIn(pair, seen, f'n={n}: rematch in round {current}')
                            seen.add(pair)
                        if m.status == Match.Status.READY:
                            complete_match(m, m.player1)
                    if current >= bracket.total_rounds:
                        break
                    generate_next_swiss_round(bracket)

    # ---- group playoff seeding ----

    def test_playoff_avoids_same_group_first_round_with_two_qualifiers(self):
        tournament, players = self._tournament(16)
        bracket = generate_group_playoff_bracket(tournament, num_groups=4)
        group_of = {}
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            group_of[m.player1_id] = m.group_label
            group_of[m.player2_id] = m.group_label
            m.status = Match.Status.COMPLETED
            m.winner_id = m.player1_id
            m.save(update_fields=['status', 'winner'])

        generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=2)
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS, round_number=1):
            if m.player1_id and m.player2_id:
                self.assertNotEqual(
                    group_of[m.player1_id], group_of[m.player2_id],
                    'two qualifiers from the same group should not meet in playoff round 1',
                )

    def test_group_playoff_supports_various_sizes_and_qualifier_counts(self):
        for n, num_groups, per_group in [(8, 2, 1), (8, 2, 2), (10, 2, 2), (12, 3, 2), (16, 4, 1), (16, 4, 2)]:
            with self.subTest(n=n, groups=num_groups, qualifiers=per_group):
                tournament, players = self._tournament(n)
                bracket = generate_group_playoff_bracket(tournament, num_groups=num_groups)
                for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
                    m.status = Match.Status.COMPLETED
                    m.winner_id = m.player1_id
                    m.save(update_fields=['status', 'winner'])

                generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=per_group)
                qualifiers = set()
                for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS, round_number=1):
                    qualifiers.update(pid for pid in (m.player1_id, m.player2_id) if pid)
                self.assertEqual(len(qualifiers), num_groups * per_group)

    # ---- determinism & validation ----

    def test_bracket_generation_is_deterministic(self):
        shapes = []
        for _ in range(2):
            tournament, players = self._tournament(13)
            bracket = generate_double_elimination_bracket(tournament)
            seed_of = {p.pk: i for i, p in enumerate(players)}
            shapes.append([
                (m.bracket_side, m.round_number, m.position,
                 seed_of.get(m.player1_id), seed_of.get(m.player2_id))
                for m in Match.objects.filter(bracket=bracket).order_by('bracket_side', 'round_number', 'position')
            ])
        self.assertEqual(shapes[0], shapes[1])

    def test_complete_match_rejects_a_non_participant(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        outsider = User.objects.create_user(email='outsider-refine@example.com', password='StrongPass123')
        with self.assertRaises(DRFValidationError):
            complete_match(match, outsider)
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.READY)
        self.assertIsNone(match.winner_id)

    def test_complete_match_rejects_double_completion(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        complete_match(match, match.player1)
        with self.assertRaises(DRFValidationError):
            complete_match(match, match.player1)

    def test_failed_generation_leaves_no_partial_bracket(self):
        tournament, players = self._tournament(3)
        with self.assertRaises(DRFValidationError):
            generate_double_elimination_bracket(tournament)
        self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())
        self.assertFalse(Match.objects.filter(tournament=tournament).exists())


class BracketTopologyInvariantTests(BracketTestMixin, APITestCase):
    """Graph-level invariants that hold regardless of results, checked across the
    participant counts where bracket construction is most likely to break: a format can
    look perfect at 8 players and be wrong at 5, 7 or 11."""

    ELIMINATION_COUNTS = [4, 5, 6, 7, 8, 9, 11, 15, 16]

    def _assert_graph_is_sound(self, bracket, n, label):
        matches = list(Match.objects.filter(bracket=bracket))

        # No slot may be fed by two different sources — otherwise one player silently
        # overwrites another when both matches complete.
        feeders = {}
        for m in matches:
            for target_id, slot, kind in (
                (m.next_match_id, m.next_match_slot, 'winner'),
                (m.loser_next_match_id, m.loser_next_match_slot, 'loser'),
            ):
                if target_id is None:
                    continue
                self.assertIsNotNone(slot, f'{label} n={n}: match {m.pk} routes its {kind} with no slot')
                self.assertNotEqual(target_id, m.pk, f'{label} n={n}: match {m.pk} feeds itself')
                key = (target_id, slot)
                self.assertNotIn(
                    key, feeders,
                    f'{label} n={n}: slot {key} fed by both match {feeders.get(key)} and {m.pk}',
                )
                feeders[key] = m.pk

        # Guarantee matches are consolation dead ends.
        for m in matches:
            if m.bracket_side == Match.Side.GUARANTEE:
                self.assertIsNone(m.next_match_id, f'{label} n={n}: guarantee match re-enters the tree')

        # Exactly one match ends the tournament; every other elimination match must
        # lead somewhere, or its winner drops out of the bracket entirely.
        terminals = [
            m for m in matches
            if m.next_match_id is None and m.bracket_side != Match.Side.GUARANTEE
        ]
        self.assertEqual(
            len(terminals), 1,
            f'{label} n={n}: expected exactly one terminal match, got '
            f'{[(m.bracket_side, m.round_number, m.position) for m in terminals]}',
        )

    def test_double_elimination_graph_invariants(self):
        for n in self.ELIMINATION_COUNTS:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_double_elimination_bracket(tournament)
                self._assert_graph_is_sound(bracket, n, 'double')

                winners = list(Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS))
                byes = {m.pk for m in bye_matches(bracket)}
                for m in winners:
                    if m.pk in byes:
                        # A bye produces no loser, so it must not route one.
                        self.assertIsNone(m.loser_next_match_id, f'n={n}: bye {m.pk} routes a loser')
                    else:
                        # Every real winners-bracket loss must have exactly one
                        # destination — that is what makes it a *second* chance.
                        self.assertIsNotNone(
                            m.loser_next_match_id, f'n={n}: winners match {m.pk} drops its loser out of the bracket',
                        )

                # Exactly one winners final, one losers final, one grand final.
                self.assertEqual(len([m for m in winners if m.next_match_id and
                                      Match.objects.get(pk=m.next_match_id).bracket_side
                                      == Match.Side.GRAND_FINAL]), 1, f'n={n}: not exactly one WB finalist')
                losers = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.LOSERS)
                lb_finals = [m for m in losers if m.next_match_id and
                             Match.objects.get(pk=m.next_match_id).bracket_side == Match.Side.GRAND_FINAL]
                self.assertEqual(len(lb_finals), 1, f'n={n}: not exactly one LB finalist')

    def test_double_elimination_every_player_survives_one_loss(self):
        """Nobody may leave the tournament on a single loss, on any result path."""
        for n in self.ELIMINATION_COUNTS:
            for trial in range(4):
                with self.subTest(n=n, trial=trial):
                    tournament, players = self._tournament(n)
                    bracket = generate_double_elimination_bracket(tournament)
                    rng = random.Random(f'de-{n}-{trial}')
                    played = self._play_all(
                        tournament, bracket, pick=lambda m: rng.choice([m.player1, m.player2]),
                    )
                    tournament.refresh_from_db()
                    self.assertIsNotNone(tournament.champion, f'n={n}: no champion')

                    losses = {}
                    for m in played:
                        loser = m.player2_id if m.winner_id == m.player1_id else m.player1_id
                        losses[loser] = losses.get(loser, 0) + 1
                    for p in players:
                        count = losses.get(p.pk, 0)
                        if p.pk == tournament.champion_id:
                            self.assertLessEqual(count, 1, f'n={n}: champion has {count} losses')
                        else:
                            self.assertEqual(
                                count, 2, f'n={n} trial={trial}: player left with {count} losses, expected 2',
                            )

    def test_single_elimination_graph_invariants(self):
        for n in [2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 15, 16]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_bracket(tournament)
                self._assert_graph_is_sound(bracket, n, 'single')
                for m in Match.objects.filter(bracket=bracket):
                    self.assertIsNone(m.loser_next_match_id, f'n={n}: single elimination routed a loser')

    def test_guarantee_graph_invariants(self):
        for n in [8, 9, 11, 15, 16]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_three_game_guarantee_bracket(tournament)
                self._assert_graph_is_sound(bracket, n, 'guarantee3')

    def test_topological_order_places_every_source_before_its_targets(self):
        """The ordering `_min_real_games_before` depends on must come from the edges,
        not from side/round metadata."""
        for n in [9, 11, 16]:
            with self.subTest(n=n):
                tournament, players = self._tournament(n)
                bracket = generate_three_game_guarantee_bracket(tournament)
                ordered = _topological_matches(bracket)
                self.assertEqual(len(ordered), Match.objects.filter(bracket=bracket).count())
                seen = set()
                for m in ordered:
                    for target_id in (m.next_match_id, m.loser_next_match_id):
                        self.assertNotIn(
                            target_id, seen, f'n={n}: match {m.pk} appears after its target {target_id}',
                        )
                    seen.add(m.pk)

    def test_group_standings_ignore_playoff_results(self):
        """A group table must not absorb playoff results once the playoff starts."""
        tournament, players = self._tournament(8)
        bracket = generate_group_playoff_bracket(tournament, num_groups=2)
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            complete_match(m, m.player1)

        group_players = {}
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            group_players.setdefault(m.group_label, set()).update([m.player1_id, m.player2_id])

        before = {
            label: {row['player'].pk: (row['wins'], row['played'])
                    for row in group_stage_standings(tournament, [p for p in players if p.pk in ids])}
            for label, ids in group_players.items()
        }

        generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=2)
        self._play_all(tournament, bracket)

        after = {
            label: {row['player'].pk: (row['wins'], row['played'])
                    for row in group_stage_standings(tournament, [p for p in players if p.pk in ids])}
            for label, ids in group_players.items()
        }
        self.assertEqual(before, after, 'playoff results leaked into the group standings')

    def test_playoff_seeding_finds_a_conflict_free_arrangement(self):
        """Backtracking should find a same-group-free first round wherever one exists,
        including group counts where a greedy repair can stall."""
        for n, num_groups, per_group in [(8, 2, 2), (12, 3, 2), (16, 4, 2), (16, 4, 4)]:
            with self.subTest(n=n, groups=num_groups, qualifiers=per_group):
                tournament, players = self._tournament(n)
                bracket = generate_group_playoff_bracket(tournament, num_groups=num_groups)
                group_of = {}
                for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
                    group_of[m.player1_id] = m.group_label
                    group_of[m.player2_id] = m.group_label
                    complete_match(m, m.player1)

                generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=per_group)
                for m in Match.objects.filter(
                    bracket=bracket, bracket_side=Match.Side.WINNERS, round_number=1,
                ):
                    if m.player1_id and m.player2_id:
                        self.assertNotEqual(
                            group_of[m.player1_id], group_of[m.player2_id],
                            f'n={n}/{num_groups} groups: same-group first-round match',
                        )

    def test_swiss_round_count_is_configurable(self):
        tournament, players = self._tournament(8)
        bracket = generate_swiss_bracket(tournament, total_rounds=5)
        self.assertEqual(bracket.total_rounds, 5)

        other, _ = self._tournament(8)
        self.assertEqual(generate_swiss_bracket(other).total_rounds, 3)  # ceil(log2(8))

    def test_bye_cannot_be_submitted_as_a_result(self):
        tournament, players = self._tournament(5)
        bracket = generate_swiss_bracket(tournament)
        bye = Match.objects.filter(bracket=bracket, player2__isnull=True).first()
        self.assertIsNotNone(bye)
        # It is already completed at generation, and cannot be re-reported.
        self.assertEqual(bye.status, Match.Status.COMPLETED)
        with self.assertRaises(DRFValidationError):
            complete_match(bye, bye.player1)


class MatchCompletionConcurrencyTests(TransactionTestCase):
    """Real threads against a real database — the row-lock behaviour in
    `complete_match` cannot be exercised inside a single wrapped transaction."""

    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        organizer_user = User.objects.create_user(email='conc-org@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=organizer_user, company_name='Conc Co')
        self.players = [
            User.objects.create_user(email=f'conc-p{i}@example.com', password='StrongPass123') for i in range(4)
        ]
        self.tournament = Tournament.objects.create(
            name='Conc Cup', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
        )
        for p in self.players:
            Registration.objects.create(tournament=self.tournament, player=p, checked_in=True)

    def test_simultaneous_completion_records_exactly_one_winner(self):
        bracket = generate_bracket(self.tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        self.assertIsNotNone(match)

        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()

        def attempt(winner_id):
            try:
                barrier.wait(timeout=10)
                complete_match(Match.objects.get(pk=match.pk), User.objects.get(pk=winner_id))
                with lock:
                    outcomes.append('completed')
            except DRFValidationError:
                with lock:
                    outcomes.append('rejected')
            finally:
                connection.close()

        threads = [
            threading.Thread(target=attempt, args=(match.player1_id,)),
            threading.Thread(target=attempt, args=(match.player2_id,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        self.assertEqual(sorted(outcomes), ['completed', 'rejected'],
                         f'both requests should not succeed, got {outcomes}')

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.COMPLETED)
        self.assertIn(match.winner_id, (match.player1_id, match.player2_id))

        # The winner must have been advanced exactly once — never both players.
        final = Match.objects.get(bracket=bracket, pk=match.next_match_id)
        advanced = [pid for pid in (final.player1_id, final.player2_id) if pid]
        self.assertEqual(advanced, [match.winner_id])


class ProductionSafetyTests(BracketTestMixin, APITestCase):
    """Guards that matter in production rather than in bracket theory: duplicate
    generation, degenerate field sizes, tie-breaking that must not fall through to
    registration order, and transactional email delivery."""

    def test_generators_reject_a_second_bracket(self):
        generators = [
            (generate_bracket, 4),
            (generate_double_elimination_bracket, 4),
            (generate_three_game_guarantee_bracket, 8),
            (generate_round_robin_bracket, 4),
            (generate_swiss_bracket, 4),
        ]
        for generator, n in generators:
            with self.subTest(generator=generator.__name__):
                tournament, _ = self._tournament(n)
                generator(tournament)
                with self.assertRaises(DRFValidationError):
                    generator(tournament)
                self.assertEqual(Bracket.objects.filter(tournament=tournament).count(), 1)

    def test_group_playoff_rejects_a_second_bracket(self):
        tournament, _ = self._tournament(8)
        generate_group_playoff_bracket(tournament, num_groups=2)
        with self.assertRaises(DRFValidationError):
            generate_group_playoff_bracket(tournament, num_groups=2)

    def test_single_elimination_rejects_degenerate_fields(self):
        for n in [0, 1]:
            with self.subTest(n=n):
                tournament, _ = self._tournament(n)
                with self.assertRaises(DRFValidationError):
                    generate_bracket(tournament)
                self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())
                self.assertFalse(Match.objects.filter(tournament=tournament).exists())

    def test_round_robin_tie_broken_by_head_to_head_not_registration_order(self):
        tournament, players = self._tournament(4)
        bracket = generate_round_robin_bracket(tournament)
        first, second, third, fourth = players

        # Engineer a three-way tie on 2 wins where the earliest registrant is *not*
        # the strongest on head-to-head.
        wanted = {
            frozenset((first.pk, second.pk)): second,
            frozenset((second.pk, third.pk)): third,
            frozenset((third.pk, first.pk)): third,
            frozenset((first.pk, fourth.pk)): first,
            frozenset((second.pk, fourth.pk)): second,
            frozenset((third.pk, fourth.pk)): fourth,
        }
        for m in Match.objects.filter(bracket=bracket):
            complete_match(m, wanted[frozenset((m.player1_id, m.player2_id))])

        rows = format_standings(tournament)
        by_id = {row['player'].pk: row for row in rows}
        self.assertEqual(by_id[first.pk]['wins'], 1)
        self.assertEqual(by_id[second.pk]['wins'], 2)
        self.assertEqual(by_id[third.pk]['wins'], 2)

        # second and third are tied on wins; third beat second head-to-head, so third
        # must rank above second even though second registered earlier.
        order = [row['player'].pk for row in rows]
        self.assertLess(order.index(third.pk), order.index(second.pk))
        self.assertEqual(by_id[third.pk]['tiebreaks']['head_to_head'], 1)
        self.assertEqual(by_id[second.pk]['tiebreaks']['head_to_head'], 0)

    def test_group_standings_use_tiebreakers(self):
        tournament, players = self._tournament(8)
        bracket = generate_group_playoff_bracket(tournament, num_groups=2)
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            complete_match(m, m.player1)
        group_ids = set()
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP, group_label='A'):
            group_ids.update([m.player1_id, m.player2_id])
        rows = group_stage_standings(tournament, [p for p in players if p.pk in group_ids])
        for row in rows:
            self.assertIn('head_to_head', row['tiebreaks'])
            self.assertIn('sonneborn_berger', row['tiebreaks'])

    def test_unknown_tiebreaker_is_rejected(self):
        tournament, _ = self._tournament(4)
        generate_round_robin_bracket(tournament)
        with self.assertRaises(DRFValidationError):
            standings(tournament, tiebreakers=['not_a_real_tiebreaker'])

    def test_group_stage_rejects_more_than_26_groups(self):
        tournament, _ = self._tournament(8)
        with self.assertRaises(DRFValidationError):
            generate_group_playoff_bracket(tournament, num_groups=27)

    def test_champion_email_is_sent_only_after_commit(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, status=Match.Status.READY):
            complete_match(m, m.player1)
        final = Match.objects.get(bracket=bracket, next_match__isnull=True)

        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            complete_match(final, final.player1)
            finalize_tournament_champion(tournament)
            # Champion is persisted, but nothing has been sent yet.
            tournament.refresh_from_db()
            self.assertIsNotNone(tournament.champion)
            self.assertEqual(len(mail.outbox), 0, 'email must not be sent before commit')
        self.assertTrue(callbacks, 'the win email should be deferred to an on_commit callback')

    def test_guarantee_structural_invariant_holds_for_every_field_size(self):
        """A proof-shaped check rather than a sampled one: for every match whose loser
        is eliminated, the loser's minimum possible real-game count must reach the
        guarantee, counting the bonus match where one is routed."""
        for n in range(8, 17):
            with self.subTest(n=n):
                tournament, _ = self._tournament(n)
                bracket = generate_three_game_guarantee_bracket(tournament)
                min_before = _min_real_games_before(bracket)

                for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.LOSERS):
                    at_elimination = min_before[m.pk] + 1
                    self.assertGreaterEqual(
                        at_elimination, 2,
                        f'n={n}: losers match {m.pk} reachable with fewer than 2 games',
                    )
                    if at_elimination < GUARANTEED_GAMES:
                        self.assertIsNotNone(
                            m.loser_next_match_id,
                            f'n={n}: losers match {m.pk} eliminates on {at_elimination} games with no bonus match',
                        )
                        bonus = Match.objects.get(pk=m.loser_next_match_id)
                        self.assertEqual(bonus.bracket_side, Match.Side.GUARANTEE)
                        self.assertGreaterEqual(at_elimination + 1, GUARANTEED_GAMES)

                # Every bonus match must be fed from both sides, or someone routed into
                # it never actually gets their extra game.
                all_matches = list(Match.objects.filter(bracket=bracket))
                for bonus in [m for m in all_matches if m.bracket_side == Match.Side.GUARANTEE]:
                    feeders = [x for x in all_matches if x.loser_next_match_id == bonus.pk]
                    self.assertEqual(len(feeders), 2, f'n={n}: bonus match {bonus.pk} has {len(feeders)} feeders')


class ConcurrentGenerationTests(TransactionTestCase):
    """Threaded tests for the read-then-write windows in bracket creation, Swiss round
    advancement and champion finalisation. Each is a check followed by a write, which
    two simultaneous requests can both pass without a row lock."""

    def _make_tournament(self, name, n):
        game = Game.objects.create(name=f'Game {name}', genre='FPS')
        organizer_user = User.objects.create_user(email=f'{name}-org@example.com', password='StrongPass123')
        organizer = Organizer.objects.create(user=organizer_user, company_name=f'{name} Co')
        players = [
            User.objects.create_user(email=f'{name}-p{i}@example.com', password='StrongPass123') for i in range(n)
        ]
        tournament = Tournament.objects.create(
            name=name, game=game, organizer=organizer, starts_at=timezone.now(),
        )
        for p in players:
            Registration.objects.create(tournament=tournament, player=p, checked_in=True)
        return tournament, players

    @staticmethod
    def _run_concurrently(fn, count=2):
        barrier = threading.Barrier(count)
        outcomes = []
        lock = threading.Lock()

        def wrapped():
            try:
                barrier.wait(timeout=10)
                fn()
                with lock:
                    outcomes.append('ok')
            except Exception as exc:  # noqa: BLE001 - the type is the assertion
                with lock:
                    outcomes.append(type(exc).__name__)
            finally:
                connection.close()

        threads = [threading.Thread(target=wrapped) for _ in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        return outcomes

    def test_simultaneous_bracket_generation_creates_exactly_one(self):
        tournament, _ = self._make_tournament('race-gen', 8)
        outcomes = self._run_concurrently(lambda: generate_bracket(tournament))

        self.assertEqual(outcomes.count('ok'), 1, f'exactly one generation should succeed, got {outcomes}')
        self.assertEqual(Bracket.objects.filter(tournament=tournament).count(), 1)
        # The loser must fail cleanly, not with a database integrity error.
        self.assertEqual(outcomes.count('ValidationError'), 1, f'expected a clean rejection, got {outcomes}')
        self.assertEqual(
            Match.objects.filter(tournament=tournament, bracket_side=Match.Side.WINNERS, round_number=1).count(), 4,
        )

    def test_simultaneous_swiss_round_generation_creates_one_round(self):
        tournament, _ = self._make_tournament('race-swiss', 8)
        bracket = generate_swiss_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, round_number=1):
            complete_match(m, m.player1)

        outcomes = self._run_concurrently(lambda: generate_next_swiss_round(bracket))

        self.assertEqual(outcomes.count('ok'), 1, f'exactly one round should be built, got {outcomes}')
        round_two = Match.objects.filter(bracket=bracket, round_number=2)
        self.assertEqual(round_two.count(), 4, 'round 2 should contain exactly one set of pairings')
        # Nobody may appear twice in the round.
        appearances = []
        for m in round_two:
            appearances.extend(pid for pid in (m.player1_id, m.player2_id) if pid)
        self.assertEqual(len(appearances), len(set(appearances)))

    def test_simultaneous_finalization_sends_one_champion_email(self):
        tournament, _ = self._make_tournament('race-champ', 4)
        bracket = generate_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, status=Match.Status.READY):
            complete_match(m, m.player1)
        final = Match.objects.get(bracket=bracket, next_match__isnull=True)
        complete_match(final, final.player1)

        mail.outbox = []
        outcomes = self._run_concurrently(lambda: finalize_tournament_champion(tournament))

        self.assertEqual(outcomes, ['ok', 'ok'], f'both calls should succeed idempotently, got {outcomes}')
        tournament.refresh_from_db()
        self.assertIsNotNone(tournament.champion)
        self.assertEqual(len(mail.outbox), 1, f'champion should be emailed exactly once, got {len(mail.outbox)}')

    def test_simultaneous_playoff_generation_creates_one_playoff(self):
        tournament, _ = self._make_tournament('race-playoff', 8)
        bracket = generate_group_playoff_bracket(tournament, num_groups=2)
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            complete_match(m, m.player1)

        outcomes = self._run_concurrently(
            lambda: generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=2),
        )

        self.assertEqual(outcomes.count('ok'), 1, f'exactly one playoff should be built, got {outcomes}')
        playoff = Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS)
        self.assertEqual(playoff.filter(round_number=1).count(), 2)


class SlotSafetyAndPairingQualityTests(BracketTestMixin, APITestCase):
    def test_routing_into_an_occupied_slot_is_rejected(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        first, second = list(Match.objects.filter(bracket=bracket, status=Match.Status.READY).order_by('position'))

        complete_match(first, first.player1)
        # Both semifinals feed the same final. Re-point the second at the slot the
        # first already filled and confirm the graph refuses to evict the occupant.
        second.next_match_slot = first.next_match_slot
        second.save(update_fields=['next_match_slot'])

        with self.assertRaises(DRFValidationError):
            complete_match(second, second.player1)

        final = Match.objects.get(pk=first.next_match_id)
        self.assertEqual(getattr(final, f'player{first.next_match_slot}_id'), first.winner_id)

    def test_dutch_split_applies_within_each_score_block(self):
        """Multi-block regression: `ideal` indexes into all remaining players, which is
        only correct because the pool stays score-ordered. A block of four must pair
        its 1st against its 3rd, not 1st against 2nd."""
        tournament, players = self._tournament(8)
        bracket = generate_swiss_bracket(tournament)

        # Round 1 is a single block of eight: top half against bottom half.
        round_one = {
            frozenset((m.player1_id, m.player2_id))
            for m in Match.objects.filter(bracket=bracket, round_number=1)
        }
        self.assertEqual(round_one, {frozenset((players[i].pk, players[i + 4].pk)) for i in range(4)})

        for m in Match.objects.filter(bracket=bracket, round_number=1, status=Match.Status.READY):
            complete_match(m, m.player1)
        generate_next_swiss_round(bracket)

        # Two even blocks now: winners players[0..3], losers players[4..7]. Each pairs
        # internally, and the Dutch split inside a block of four is 1v3 / 2v4.
        round_two = {
            frozenset((m.player1_id, m.player2_id))
            for m in Match.objects.filter(bracket=bracket, round_number=2)
        }
        self.assertEqual(round_two, {
            frozenset((players[0].pk, players[2].pk)),
            frozenset((players[1].pk, players[3].pk)),
            frozenset((players[4].pk, players[6].pk)),
            frozenset((players[5].pk, players[7].pk)),
        })

    def test_odd_score_blocks_float_exactly_one_player(self):
        """With ten players both blocks are odd after round 1, so Swiss must float
        across scores — pairing strictly within blocks is impossible."""
        tournament, players = self._tournament(10)
        bracket = generate_swiss_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, round_number=1, status=Match.Status.READY):
            complete_match(m, m.player1)
        generate_next_swiss_round(bracket)

        wins = {row['player'].pk: row['wins'] for row in standings(tournament)}
        cross_score = [
            m for m in Match.objects.filter(bracket=bracket, round_number=2)
            if m.player2_id and wins[m.player1_id] != wins[m.player2_id]
        ]
        self.assertEqual(len(cross_score), 1, 'exactly one float is needed to bridge two odd blocks')
        self.assertEqual(
            abs(wins[cross_score[0].player1_id] - wins[cross_score[0].player2_id]), 1,
            'a float should bridge adjacent scores, not jump the table',
        )


class LockOrderAuditTests(SimpleTestCase):
    """Guards the Tournament -> Bracket -> Match lock ordering documented at the top of
    `services.py`. Deadlock-freedom rests on that single global order, and a new
    `select_for_update()` added later in the wrong place would silently reintroduce a
    cycle — no ordinary test would fail. This one does."""

    #: Every lock site the ordering argument has accounted for, and what it locks.
    APPROVED_SITES = {
        '_lock_tournament': 'Tournament',
        '_lock_bracket': 'Bracket',
        '_advance_into': 'Match',
        '_retract_from': 'Match',
        '_downstream_reachable': 'Match',
        'complete_match': 'Match',
        'override_match_result': 'Match',
    }

    def _lock_sites(self):
        """(enclosing function, locked model) for every select_for_update in services."""
        source = Path(services.__file__).read_text()
        tree = ast.parse(source)
        sites = []
        for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == 'select_for_update':
                    model = None
                    inner = func.value
                    if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
                        model = inner.value.id  # e.g. Tournament.objects
                    sites.append((function.name, model))
        return sites

    def test_every_lock_site_is_accounted_for(self):
        for function_name, model in self._lock_sites():
            self.assertIn(
                function_name, self.APPROVED_SITES,
                f'{function_name}() takes a row lock but is not covered by the '
                f'Tournament -> Bracket -> Match ordering argument. Either route it '
                f'through _lock_tournament/_lock_bracket, or extend APPROVED_SITES '
                f'once you have checked it cannot invert the order.',
            )
            self.assertEqual(
                self.APPROVED_SITES[function_name], model,
                f'{function_name}() locks {model}, expected {self.APPROVED_SITES[function_name]}',
            )

    def test_tournament_and_bracket_locks_go_through_the_helpers(self):
        """Only the two helpers may lock Tournament or Bracket, so the ordering rule has
        a single place to be enforced and audited."""
        for function_name, model in self._lock_sites():
            if model in ('Tournament', 'Bracket'):
                self.assertIn(
                    function_name, ('_lock_tournament', '_lock_bracket'),
                    f'{function_name}() locks {model} directly; use the helper instead',
                )

    def test_complete_match_locks_the_tournament_before_the_match(self):
        """The specific inversion this ordering exists to prevent: locking the match
        first and the tournament afterwards is the natural implementation, and is the
        opposite order from bracket generation."""
        source = inspect.getsource(services.complete_match)
        tournament_lock = source.index('_lock_tournament')
        match_lock = source.index('Match.objects.select_for_update()')
        self.assertLess(
            tournament_lock, match_lock,
            'complete_match must take the tournament lock before the match lock',
        )

    def test_override_match_result_locks_the_tournament_before_the_match(self):
        source = inspect.getsource(services.override_match_result)
        tournament_lock = source.index('_lock_tournament')
        match_lock = source.index('Match.objects.select_for_update()')
        self.assertLess(
            tournament_lock, match_lock,
            'override_match_result must take the tournament lock before the match lock',
        )


class TransactionRollbackTests(BracketTestMixin, APITestCase):
    """A failure part-way through a multi-row operation must leave nothing behind."""

    def test_failed_bracket_generation_rolls_back_every_row(self):
        tournament, _ = self._tournament(11)
        boom = Exception('injected failure after matches were created')
        with mock.patch.object(services, '_attach_grand_final', side_effect=boom):
            with self.assertRaises(Exception):
                generate_double_elimination_bracket(tournament)

        self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())
        self.assertFalse(Match.objects.filter(tournament=tournament).exists())

    def test_failed_swiss_round_rolls_back(self):
        tournament, _ = self._tournament(8)
        bracket = generate_swiss_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, round_number=1):
            complete_match(m, m.player1)
        before = Match.objects.filter(bracket=bracket).count()

        with mock.patch.object(services, '_swiss_pairings', side_effect=Exception('boom')):
            with self.assertRaises(Exception):
                generate_next_swiss_round(bracket)

        self.assertEqual(Match.objects.filter(bracket=bracket).count(), before)
        self.assertFalse(Match.objects.filter(bracket=bracket, round_number=2).exists())

    def test_failed_playoff_generation_rolls_back(self):
        tournament, _ = self._tournament(8)
        bracket = generate_group_playoff_bracket(tournament, num_groups=2)
        for m in Match.objects.filter(bracket=bracket, bracket_side=Match.Side.GROUP):
            complete_match(m, m.player1)
        before = Match.objects.filter(bracket=bracket).count()

        with mock.patch.object(services, '_build_single_elim', side_effect=Exception('boom')):
            with self.assertRaises(Exception):
                generate_group_playoff_bracket_phase2(bracket, qualifiers_per_group=2)

        self.assertEqual(Match.objects.filter(bracket=bracket).count(), before)
        self.assertFalse(
            Match.objects.filter(bracket=bracket, bracket_side=Match.Side.WINNERS).exists(),
        )

    def test_failed_propagation_rolls_back_the_completion(self):
        """If advancing the winner fails, the match must not stay marked completed."""
        tournament, _ = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()

        with mock.patch.object(services, '_advance_into', side_effect=Exception('boom')):
            with self.assertRaises(Exception):
                complete_match(match, match.player1)

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.READY)
        self.assertIsNone(match.winner_id)

    def test_failed_champion_email_does_not_roll_back_the_result(self):
        """The win email is deferred to on_commit precisely so a mail failure cannot
        undo a legitimate match result."""
        tournament, _ = self._tournament(4)
        bracket = generate_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, status=Match.Status.READY):
            complete_match(m, m.player1)
        final = Match.objects.get(bracket=bracket, next_match__isnull=True)

        with mock.patch('tourny_regist.emails.send_tournament_win_email', side_effect=Exception('smtp down')):
            with self.captureOnCommitCallbacks(execute=False):
                complete_match(final, final.player1)
                finalize_tournament_champion(tournament)

        final.refresh_from_db()
        tournament.refresh_from_db()
        self.assertEqual(final.status, Match.Status.COMPLETED)
        self.assertIsNotNone(tournament.champion)


class IdempotencyAndConstraintTests(BracketTestMixin, APITestCase):
    def test_retrying_a_lost_result_submission_is_rejected_not_duplicated(self):
        """A client whose response was lost retries the same result. The second attempt
        must be refused rather than double-advancing anyone."""
        tournament, _ = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()

        complete_match(match, match.player1)
        winner_id = match.winner_id
        final = Match.objects.get(pk=match.next_match_id)
        occupant = getattr(final, f'player{match.next_match_slot}_id')

        with self.assertRaises(DRFValidationError):
            complete_match(Match.objects.get(pk=match.pk), User.objects.get(pk=winner_id))

        final.refresh_from_db()
        self.assertEqual(getattr(final, f'player{match.next_match_slot}_id'), occupant)
        self.assertEqual(Match.objects.get(pk=match.pk).winner_id, winner_id)

    def test_repeated_finalization_is_idempotent(self):
        tournament, _ = self._tournament(4)
        bracket = generate_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, status=Match.Status.READY):
            complete_match(m, m.player1)
        final = Match.objects.get(bracket=bracket, next_match__isnull=True)
        complete_match(final, final.player1)

        mail.outbox = []
        with self.captureOnCommitCallbacks(execute=True):
            first = finalize_tournament_champion(tournament)
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(5):
                finalize_tournament_champion(tournament)

        self.assertIsNotNone(first)
        self.assertEqual(len(mail.outbox), 1, 'the champion must only ever be emailed once')

    def test_database_rejects_a_duplicate_bracket_even_without_app_locking(self):
        """Correctness must not rest on application locking alone."""
        tournament, _ = self._tournament(4)
        generate_bracket(tournament)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Bracket.objects.create(tournament=tournament, total_rounds=2)

    def test_database_rejects_two_matches_in_the_same_slot(self):
        tournament, _ = self._tournament(4)
        bracket = generate_bracket(tournament)
        existing = Match.objects.filter(bracket=bracket, round_number=1).first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Match.objects.create(
                    bracket=bracket, tournament=tournament,
                    bracket_side=existing.bracket_side,
                    round_number=existing.round_number,
                    position=existing.position,
                )


class HighContentionTests(TransactionTestCase):
    """Many simultaneous requests, not just two. Each scenario must end in exactly one
    valid state and must not deadlock."""

    THREADS = 12

    def _make_tournament(self, name, n):
        game = Game.objects.create(name=f'Game {name}', genre='FPS')
        organizer_user = User.objects.create_user(email=f'{name}-org@example.com', password='StrongPass123')
        organizer = Organizer.objects.create(user=organizer_user, company_name=f'{name} Co')
        players = [
            User.objects.create_user(email=f'{name}-p{i}@example.com', password='StrongPass123') for i in range(n)
        ]
        tournament = Tournament.objects.create(name=name, game=game, organizer=organizer, starts_at=timezone.now())
        for p in players:
            Registration.objects.create(tournament=tournament, player=p, checked_in=True)
        return tournament, players

    def _storm(self, fn, threads=None):
        threads = threads or self.THREADS
        barrier = threading.Barrier(threads)
        outcomes = []
        lock = threading.Lock()

        def wrapped(index):
            try:
                barrier.wait(timeout=20)
                fn(index)
                with lock:
                    outcomes.append('ok')
            except Exception as exc:  # noqa: BLE001 - the type is what we assert on
                with lock:
                    outcomes.append(type(exc).__name__)
            finally:
                connection.close()

        workers = [threading.Thread(target=wrapped, args=(i,)) for i in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=60)
        self.assertEqual(len(outcomes), threads, 'a thread hung — likely a deadlock')
        self.assertNotIn('OperationalError', outcomes, f'database deadlock detected: {outcomes}')
        return outcomes

    def test_many_simultaneous_bracket_generations(self):
        tournament, _ = self._make_tournament('storm-gen', 8)
        outcomes = self._storm(lambda i: generate_bracket(tournament))
        self.assertEqual(outcomes.count('ok'), 1, f'exactly one generation may succeed: {outcomes}')
        self.assertEqual(Bracket.objects.filter(tournament=tournament).count(), 1)
        # 8 players single elimination: 4 + 2 + 1 matches, from one generation only.
        self.assertEqual(Match.objects.filter(tournament=tournament).count(), 7)

    def test_many_simultaneous_completions_of_one_match(self):
        tournament, _ = self._make_tournament('storm-match', 8)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        candidates = [match.player1_id, match.player2_id]

        outcomes = self._storm(
            lambda i: complete_match(Match.objects.get(pk=match.pk), User.objects.get(pk=candidates[i % 2])),
        )
        self.assertEqual(outcomes.count('ok'), 1, f'exactly one result may be recorded: {outcomes}')

        match.refresh_from_db()
        final = Match.objects.get(pk=match.next_match_id)
        advanced = [pid for pid in (final.player1_id, final.player2_id) if pid]
        self.assertEqual(advanced, [match.winner_id], 'exactly one player may advance')

    def test_many_simultaneous_completions_of_different_matches(self):
        """Different matches in one tournament serialize on the tournament row; all
        should still succeed, and the bracket must end consistent."""
        tournament, _ = self._make_tournament('storm-parallel', 16)
        bracket = generate_bracket(tournament)
        ready = list(Match.objects.filter(bracket=bracket, status=Match.Status.READY).order_by('position'))
        self.assertEqual(len(ready), 8)

        outcomes = self._storm(
            lambda i: complete_match(Match.objects.get(pk=ready[i].pk), Match.objects.get(pk=ready[i].pk).player1),
            threads=8,
        )
        self.assertEqual(outcomes.count('ok'), 8, f'independent matches should all record: {outcomes}')

        round_two = Match.objects.filter(bracket=bracket, round_number=2)
        self.assertEqual(round_two.count(), 4)
        for m in round_two:
            self.assertIsNotNone(m.player1_id)
            self.assertIsNotNone(m.player2_id)
            self.assertNotEqual(m.player1_id, m.player2_id)
            self.assertEqual(m.status, Match.Status.READY)

    def test_many_simultaneous_swiss_advancements(self):
        tournament, _ = self._make_tournament('storm-swiss', 8)
        bracket = generate_swiss_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, round_number=1):
            complete_match(m, m.player1)

        outcomes = self._storm(lambda i: generate_next_swiss_round(bracket))
        self.assertEqual(outcomes.count('ok'), 1, f'exactly one round may be built: {outcomes}')
        self.assertEqual(Match.objects.filter(bracket=bracket, round_number=2).count(), 4)

    def test_many_simultaneous_finalizations(self):
        tournament, _ = self._make_tournament('storm-champ', 4)
        bracket = generate_bracket(tournament)
        for m in Match.objects.filter(bracket=bracket, status=Match.Status.READY):
            complete_match(m, m.player1)
        final = Match.objects.get(bracket=bracket, next_match__isnull=True)
        complete_match(final, final.player1)

        mail.outbox = []
        outcomes = self._storm(lambda i: finalize_tournament_champion(tournament))
        self.assertEqual(outcomes.count('ok'), self.THREADS, f'finalisation is idempotent: {outcomes}')
        self.assertEqual(len(mail.outbox), 1, f'champion emailed {len(mail.outbox)} times')

    def test_mixed_workload_does_not_deadlock(self):
        """The scenario the lock ordering exists for: generation (Tournament -> Match)
        interleaved with completion (Tournament -> Match) and finalisation, all against
        the same tournament at once."""
        tournament, _ = self._make_tournament('storm-mixed', 8)
        bracket = generate_bracket(tournament)
        ready = list(Match.objects.filter(bracket=bracket, status=Match.Status.READY).order_by('position'))

        def work(index):
            action = index % 3
            if action == 0:
                generate_bracket(tournament)          # will be rejected, but takes the locks
            elif action == 1:
                target = ready[index % len(ready)]
                complete_match(Match.objects.get(pk=target.pk), Match.objects.get(pk=target.pk).player1)
            else:
                finalize_tournament_champion(tournament)

        outcomes = self._storm(work)
        self.assertNotIn('OperationalError', outcomes)
        for m in Match.objects.filter(bracket=bracket):
            if m.player1_id and m.player2_id:
                self.assertNotEqual(m.player1_id, m.player2_id)
        self.assertEqual(Bracket.objects.filter(tournament=tournament).count(), 1)


class BracketPreviewTests(BracketTestMixin, APITestCase):
    def test_preview_single_elimination_no_writes(self):
        tournament, players = self._tournament(5)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/brackets/preview/', {'bracket_format': 'single'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['player_count'], 5)
        self.assertEqual(resp.data['bracket_size'], 8)
        self.assertEqual(len(resp.data['round1']), 4)
        self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())
        self.assertFalse(Match.objects.filter(tournament=tournament).exists())

    def test_preview_insufficient_players_reports_error_not_500(self):
        tournament, players = self._tournament(1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/brackets/preview/', {'bracket_format': 'single'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('error', resp.data)

    def test_preview_round_robin(self):
        tournament, players = self._tournament(4)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/brackets/preview/', {'bracket_format': 'round_robin'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['total_rounds'], 3)

    def test_preview_cross_organizer_forbidden(self):
        tournament, players = self._tournament(5)
        other_user = User.objects.create_user(email='other-preview@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Preview Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/brackets/preview/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class BracketResetTests(BracketTestMixin, APITestCase):
    def test_reset_before_any_real_result_is_immediate(self):
        tournament, players = self._tournament(4)
        generate_bracket(tournament)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': 'wrong format'})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())
        self.assertFalse(Match.objects.filter(tournament=tournament).exists())

    def test_reset_requires_reason(self):
        tournament, players = self._tournament(4)
        generate_bracket(tournament)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': ''})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_with_no_bracket_rejected(self):
        tournament, players = self._tournament(4)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_cross_organizer_forbidden(self):
        tournament, players = self._tournament(4)
        generate_bracket(tournament)
        other_user = User.objects.create_user(email='other-reset@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Reset Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_reset_after_real_result_requires_admin_review(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        complete_match(match, match.player1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': 'contested result'})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED, resp.data)
        self.assertTrue(Bracket.objects.filter(tournament=tournament).exists())
        review_request = AdminReviewRequest.objects.get(
            object_id=tournament.pk, request_type=AdminReviewRequest.RequestType.BRACKET_RESET,
        )
        self.assertEqual(review_request.status, AdminReviewRequest.Status.PENDING)

    def test_admin_approving_review_request_resets_the_bracket(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        complete_match(match, match.player1)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.BRACKET_RESET,
            reason='contested', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        admin = User.objects.create_user(email='bracket-admin@example.com', password='StrongPass123', is_staff=True)
        self.client.force_authenticate(user=admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertFalse(Bracket.objects.filter(tournament=tournament).exists())

    def test_admin_rejecting_review_request_leaves_bracket_untouched(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.filter(bracket=bracket, status=Match.Status.READY).first()
        complete_match(match, match.player1)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.BRACKET_RESET,
            reason='contested', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        admin = User.objects.create_user(email='bracket-admin2@example.com', password='StrongPass123', is_staff=True)
        self.client.force_authenticate(user=admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'rejected'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(Bracket.objects.filter(tournament=tournament).exists())

    def test_reset_clears_declared_champion(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        complete_match(match, match.player1)
        finalize_tournament_champion(tournament)
        tournament.refresh_from_db()
        self.assertIsNotNone(tournament.champion_id)

        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.BRACKET_RESET,
            reason='x', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        admin = User.objects.create_user(email='champ-reset-admin@example.com', password='StrongPass123', is_staff=True)
        self.client.force_authenticate(user=admin)
        self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'approved'})
        tournament.refresh_from_db()
        self.assertIsNone(tournament.champion_id)

    def test_regenerate_after_reset(self):
        """reset + the existing generate endpoint together *are* regenerate/reseed —
        no separate primitive exists, by design (see reset_bracket's docstring)."""
        tournament, players = self._tournament(4)
        generate_bracket(tournament)
        self.client.force_authenticate(user=self.organizer_user)
        self.client.post(f'/api/tournaments/{tournament.pk}/brackets/reset/', {'reason': 'switch format'})
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/brackets/', {'format': 'round_robin'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Bracket.objects.get(tournament=tournament).format, Bracket.Format.ROUND_ROBIN)


class ManualSeedingTests(BracketTestMixin, APITestCase):
    def test_seed_players_respects_manual_seed(self):
        tournament, players = self._tournament(4)
        Registration.objects.filter(tournament=tournament, player=players[3]).update(seed=1)
        ordered = services.seed_players(tournament)
        self.assertEqual(ordered[0], players[3])

    def test_seeding_endpoint_updates_seed(self):
        tournament, players = self._tournament(4)
        registration = Registration.objects.get(tournament=tournament, player=players[0])
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/seeding/', {
            'seeds': [{'registration_id': registration.pk, 'seed': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        registration.refresh_from_db()
        self.assertEqual(registration.seed, 1)

    def test_seeding_blocked_once_bracket_exists(self):
        tournament, players = self._tournament(4)
        generate_bracket(tournament)
        registration = Registration.objects.get(tournament=tournament, player=players[0])
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/seeding/', {
            'seeds': [{'registration_id': registration.pk, 'seed': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seeding_cross_organizer_forbidden(self):
        tournament, players = self._tournament(4)
        other_user = User.objects.create_user(email='other-seed@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Seed Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/seeding/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MatchOverrideTests(BracketTestMixin, APITestCase):
    def test_override_before_advancement_swaps_winner_and_readvances(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        m1 = Match.objects.get(bracket=bracket, round_number=1, position=0)
        complete_match(m1, m1.player1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/matches/{m1.pk}/override/',
            {'winner': m1.player2_id, 'score': 'corrected', 'reason': 'wrong player recorded'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        m1.refresh_from_db()
        self.assertEqual(m1.winner_id, m1.player2_id)
        self.assertEqual(m1.score, 'corrected')
        # the corrected winner, not the original one, must be the one who advanced
        next_match = Match.objects.get(pk=m1.next_match_id)
        self.assertEqual(m1.player2_id, next_match.player1_id if m1.next_match_slot == 1 else next_match.player2_id)

    def test_override_rejected_once_downstream_match_completed(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        m1 = Match.objects.get(bracket=bracket, round_number=1, position=0)
        m2 = Match.objects.get(bracket=bracket, round_number=1, position=1)
        complete_match(m1, m1.player1)
        complete_match(m2, m2.player1)
        final = Match.objects.get(pk=m1.next_match_id)
        complete_match(final, final.player1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/matches/{m1.pk}/override/',
            {'winner': m1.player2_id, 'reason': 'too late now'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        m1.refresh_from_db()
        self.assertEqual(m1.winner_id, m1.player1_id)

    def test_override_requires_reason(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        complete_match(match, match.player1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/matches/{match.pk}/override/', {'winner': match.player2_id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_override_rejected_for_incomplete_match(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/matches/{match.pk}/override/', {'winner': match.player1_id, 'reason': 'x'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_override_corrects_declared_champion(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        complete_match(match, match.player1)
        finalize_tournament_champion(tournament)
        tournament.refresh_from_db()
        self.assertEqual(tournament.champion_id, match.player1_id)

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/matches/{match.pk}/override/', {'winner': match.player2_id, 'reason': 'wrong winner'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        tournament.refresh_from_db()
        self.assertEqual(tournament.champion_id, match.player2_id)

    def test_override_cross_organizer_forbidden(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        complete_match(match, match.player1)
        other_user = User.objects.create_user(email='other-override@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Override Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.patch(
            f'/api/matches/{match.pk}/override/', {'winner': match.player2_id, 'reason': 'x'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MatchForfeitTests(BracketTestMixin, APITestCase):
    def test_forfeit_awards_opponent_and_advances(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket, round_number=1, position=0)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(
            f'/api/matches/{match.pk}/forfeit/',
            {'forfeiting_player': match.player1_id, 'reason': 'no-show'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        match.refresh_from_db()
        self.assertEqual(match.winner_id, match.player2_id)
        self.assertTrue(match.is_forfeit)
        self.assertEqual(match.forfeited_by_id, match.player1_id)
        self.assertEqual(match.status, Match.Status.COMPLETED)

    def test_forfeit_requires_reason(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/matches/{match.pk}/forfeit/', {'forfeiting_player': match.player1_id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forfeit_rejected_once_completed(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        complete_match(match, match.player1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(
            f'/api/matches/{match.pk}/forfeit/',
            {'forfeiting_player': match.player2_id, 'reason': 'late'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forfeit_rejects_non_participant(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        outsider = User.objects.create_user(email='outsider@example.com', password='StrongPass123')
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(
            f'/api/matches/{match.pk}/forfeit/', {'forfeiting_player': outsider.pk, 'reason': 'x'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_forfeit_cross_organizer_forbidden(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        other_user = User.objects.create_user(email='other-forfeit@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Forfeit Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.post(
            f'/api/matches/{match.pk}/forfeit/', {'forfeiting_player': match.player1_id, 'reason': 'x'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MatchScheduleAndNotesTests(BracketTestMixin, APITestCase):
    def test_schedule_match(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        when = timezone.now() + timezone.timedelta(days=1)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/matches/{match.pk}/schedule/', {'scheduled_at': when.isoformat()}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        match.refresh_from_db()
        self.assertIsNotNone(match.scheduled_at)

    def test_schedule_cross_organizer_forbidden(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        other_user = User.objects.create_user(email='other-sched@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Sched Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.patch(
            f'/api/matches/{match.pk}/schedule/', {'scheduled_at': timezone.now().isoformat()}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_notes_roundtrip_and_staff_gate(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/matches/{match.pk}/notes/', {'organizer_notes': 'keep an eye on lag'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        resp = self.client.get(f'/api/matches/{match.pk}/notes/')
        self.assertEqual(resp.data['organizer_notes'], 'keep an eye on lag')

    def test_notes_never_leak_through_the_public_match_serializer(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        match.organizer_notes = 'private organizer note'
        match.save(update_fields=['organizer_notes'])
        self.client.force_authenticate(user=players[0])
        resp = self.client.get(f'/api/matches/{match.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('organizer_notes', resp.data)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/brackets/')
        self.assertNotIn('private organizer note', str(resp.data))

    def test_notes_cross_organizer_forbidden(self):
        tournament, players = self._tournament(2)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket)
        other_user = User.objects.create_user(email='other-notes@example.com', password='StrongPass123')
        Organizer.objects.create(user=other_user, company_name='Other Notes Co')
        self.client.force_authenticate(user=other_user)
        resp = self.client.patch(f'/api/matches/{match.pk}/notes/', {'organizer_notes': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class DisqualificationForfeitsBracketMatchesTests(BracketTestMixin, APITestCase):
    def test_disqualifying_a_registration_forfeits_their_ready_match(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket, round_number=1, position=0)
        registration = Registration.objects.get(tournament=tournament, player=match.player1)

        disqualify_registration(registration, self.organizer_user, 'cheating')

        match.refresh_from_db()
        self.assertTrue(match.is_forfeit)
        self.assertEqual(match.forfeited_by_id, registration.player_id)
        self.assertEqual(match.winner_id, match.player2_id)

    def test_disqualifying_before_a_bracket_exists_does_not_touch_matches(self):
        tournament, players = self._tournament(4)
        registration = Registration.objects.get(tournament=tournament, player=players[0])
        disqualified = disqualify_registration(registration, self.organizer_user, 'no-show')
        self.assertEqual(disqualified.status, Registration.Status.DISQUALIFIED)

    def test_disqualifying_a_player_with_no_live_match_is_a_no_op_on_the_bracket(self):
        tournament, players = self._tournament(4)
        bracket = generate_bracket(tournament)
        match = Match.objects.get(bracket=bracket, round_number=1, position=0)
        complete_match(match, match.player1)
        loser_registration = Registration.objects.get(tournament=tournament, player=match.player2)
        # already eliminated — no READY match left to forfeit
        disqualify_registration(loser_registration, self.organizer_user, 'after the fact')
        match.refresh_from_db()
        self.assertFalse(match.is_forfeit)
