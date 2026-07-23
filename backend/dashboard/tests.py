from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from brackets.models import Match
from brackets.services import generate_bracket
from core.models import Follow
from games.models import Game
from organizer.models import Organizer
from partners.models import Partner
from tourny_regist.models import Registration, Tournament

User = get_user_model()


class DashboardApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        Partner.objects.create(name='Red Bull')
        Partner.objects.create(name='Inactive Co', is_active=False)

        self.organizer_user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(
            user=self.organizer_user, company_name='Acme Esports', status=Organizer.Status.APPROVED,
        )

        self.pending_organizer_user = User.objects.create_user(email='pending-org@example.com', password='StrongPass123')
        Organizer.objects.create(user=self.pending_organizer_user, company_name='Pending Co')

        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)

        self.players = [
            User.objects.create_user(email=f'player{i}@example.com', password='StrongPass123') for i in range(4)
        ]
        self.player = self.players[0]

        self.tournament = Tournament.objects.create(
            name='Winter Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now() + timezone.timedelta(days=1),
        )
        for p in self.players:
            Registration.objects.create(tournament=self.tournament, player=p, checked_in=True)
        generate_bracket(self.tournament)

        Follow.objects.create(follower=self.players[1], following=self.player)
        Follow.objects.create(follower=self.player, following=self.players[2])

        self.client.force_authenticate(user=self.player)

    def test_player_dashboard_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/dashboard/player/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_player_dashboard(self):
        resp = self.client.get('/api/dashboard/player/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['profile']['email'], 'player0@example.com')
        self.assertEqual(resp.data['followers_count'], 1)
        self.assertEqual(resp.data['following_count'], 1)
        self.assertEqual(resp.data['registrations_count'], 1)
        self.assertEqual(resp.data['upcoming_tournaments_count'], 1)
        self.assertFalse(resp.data['is_organizer'])
        self.assertIsNone(resp.data['organizer_status'])

    def test_player_dashboard_shows_upcoming_match(self):
        resp = self.client.get('/api/dashboard/player/')
        matches = resp.data['upcoming_matches']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['tournament'], 'Winter Cup')

    def test_player_dashboard_organizer_flag(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get('/api/dashboard/player/')
        self.assertTrue(resp.data['is_organizer'])
        self.assertEqual(resp.data['organizer_status'], 'approved')

    def test_organizer_dashboard_requires_registration(self):
        resp = self.client.get('/api/dashboard/organizer/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_organizer_dashboard(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get('/api/dashboard/organizer/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['organizer']['company_name'], 'Acme Esports')
        self.assertEqual(resp.data['tournaments_count'], 1)
        self.assertEqual(resp.data['total_registrations'], 4)
        self.assertEqual(resp.data['matches_awaiting_result'], 2)
        self.assertEqual(len(resp.data['tournaments']), 1)
        self.assertEqual(resp.data['tournaments'][0]['registrations_count'], 4)

    def test_organizer_dashboard_isolated_per_organizer(self):
        self.client.force_authenticate(user=self.pending_organizer_user)
        resp = self.client.get('/api/dashboard/organizer/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['tournaments_count'], 0)

    def test_admin_dashboard_forbidden_for_non_admin(self):
        resp = self.client.get('/api/dashboard/admin/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_dashboard(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get('/api/dashboard/admin/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_organizers'], 2)
        self.assertEqual(resp.data['organizers_by_status']['approved'], 1)
        self.assertEqual(resp.data['organizers_by_status']['pending'], 1)
        self.assertEqual(resp.data['organizers_by_status']['rejected'], 0)
        self.assertEqual(resp.data['total_games'], 1)
        self.assertEqual(resp.data['total_tournaments'], 1)
        self.assertEqual(resp.data['total_registrations'], 4)
        self.assertEqual(resp.data['total_partners'], 2)

    def test_stats_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stats(self):
        resp = self.client.get('/api/dashboard/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_organizers'], 1)  # only approved counted
        self.assertEqual(resp.data['total_games'], 1)
        self.assertEqual(resp.data['total_tournaments'], 1)
        self.assertEqual(resp.data['total_partners'], 1)  # only active counted
        self.assertEqual(resp.data['total_matches_played'], 0)

    def test_stats_reflects_completed_matches(self):
        match = Match.objects.filter(tournament=self.tournament, round_number=1).first()
        self.client.force_authenticate(user=self.organizer_user)
        self.client.patch(f'/api/matches/{match.pk}/result/', {'winner': match.player1_id})
        resp = self.client.get('/api/dashboard/stats/')
        self.assertEqual(resp.data['total_matches_played'], 1)
