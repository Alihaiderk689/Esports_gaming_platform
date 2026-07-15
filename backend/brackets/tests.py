from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from brackets.models import Match
from games.models import Game
from organizer.models import Organizer
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
            Registration.objects.create(tournament=tournament, player=player)

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
