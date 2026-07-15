from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Game
from organizer.models import Organizer
from tourny_regist.models import Registration, Tournament

User = get_user_model()


class TournamentRegistrationApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')

        self.organizer_user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Acme Esports')

        self.other_organizer_user = User.objects.create_user(email='other-organizer@example.com', password='StrongPass123')
        self.other_organizer = Organizer.objects.create(user=self.other_organizer_user, company_name='Other Co')

        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)

        self.player = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.other_player = User.objects.create_user(email='other-player@example.com', password='StrongPass123')

        self.tournament = Tournament.objects.create(
            name='Winter Cup', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.player)

    def test_register_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/registrations/', {'tournament': self.tournament.pk})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_register(self):
        resp = self.client.post('/api/registrations/', {'tournament': self.tournament.pk})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['tournament'], self.tournament.pk)
        self.assertEqual(resp.data['player_email'], 'player@example.com')
        self.assertFalse(resp.data['checked_in'])
        self.assertTrue(Registration.objects.filter(tournament=self.tournament, player=self.player).exists())

    def test_register_duplicate_rejected(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        resp = self.client.post('/api/registrations/', {'tournament': self.tournament.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_closed_tournament_rejected(self):
        self.tournament.is_registration_open = False
        self.tournament.save()
        resp = self.client.post('/api/registrations/', {'tournament': self.tournament.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_full_tournament_rejected(self):
        self.tournament.max_participants = 1
        self.tournament.save()
        Registration.objects.create(tournament=self.tournament, player=self.other_player)
        resp = self.client.post('/api/registrations/', {'tournament': self.tournament.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_own_registration(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        resp = self.client.delete(f'/api/registrations/{registration.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Registration.objects.filter(pk=registration.pk).exists())

    def test_delete_other_players_registration_forbidden(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.other_player)
        resp = self.client.delete(f'/api/registrations/{registration.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Registration.objects.filter(pk=registration.pk).exists())

    def test_admin_can_delete_any_registration(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.other_player)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/registrations/{registration.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_my_registrations(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        Registration.objects.create(tournament=self.tournament, player=self.other_player)
        resp = self.client.get('/api/registrations/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['player_email'], 'player@example.com')

    def test_tournament_registrations_forbidden_for_player(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_tournament_registrations_forbidden_for_other_organizer(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_tournament_registrations_allowed_for_owning_organizer(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = self._results(resp)
        self.assertEqual(len(results), 1)

    def test_tournament_registrations_allowed_for_admin(self):
        Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_checkin_forbidden_for_player(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_checkin_allowed_for_organizer(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['checked_in'])
        registration.refresh_from_db()
        self.assertTrue(registration.checked_in)
        self.assertIsNotNone(registration.checked_in_at)

    def test_checkin_allowed_for_admin(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_checkin_twice_rejected(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player, checked_in=True)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkin_forbidden_for_other_organizer(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
