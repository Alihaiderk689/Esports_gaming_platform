from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Game
from organizer.models import Organizer
from tourny_regist.models import Announcement, Registration, Team, Tournament
from tourny_regist.serializers import TournamentApplicationSerializer

User = get_user_model()

_PDF_BYTES = b'%PDF-1.4\n' + b'fake pdf body'.ljust(16, b'\x00')


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
        resp = self.client.post('/api/registrations/', {
            'tournament': self.tournament.pk,
            'full_name': 'Test Player',
            'gaming_username': 'TestTag',
            'phone_number': '+923001234567',
            'contact_email': 'player@example.com',
            'country': 'Pakistan',
            'city': 'Lahore',
            'platform': 'Steam',
            'platform_username': 'testplayer',
            'accepted_rules': True,
            'accepted_code_of_conduct': True,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['tournament'], self.tournament.pk)
        self.assertEqual(resp.data['player_email'], 'player@example.com')
        self.assertEqual(resp.data['status'], 'approved')
        self.assertFalse(resp.data['checked_in'])
        self.assertTrue(Registration.objects.filter(tournament=self.tournament, player=self.player).exists())

    def test_register_requires_rules_acceptance(self):
        resp = self.client.post('/api/registrations/', {
            'tournament': self.tournament.pk,
            'full_name': 'Test Player',
            'gaming_username': 'TestTag',
            'phone_number': '+923001234567',
            'contact_email': 'player@example.com',
            'country': 'Pakistan',
            'city': 'Lahore',
            'platform': 'Steam',
            'platform_username': 'testplayer',
            'accepted_code_of_conduct': True,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_undo_checkin(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player, checked_in=True)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/', {'checked_in': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['checked_in'])
        registration.refresh_from_db()
        self.assertFalse(registration.checked_in)
        self.assertIsNone(registration.checked_in_at)

    def test_undo_checkin_when_not_checked_in_rejected(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/', {'checked_in': False})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_registration_cannot_be_checked_in(self):
        registration = Registration.objects.create(
            tournament=self.tournament, player=self.player, status=Registration.Status.REJECTED,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_reject_captures_reason_and_undoes_checkin(self):
        registration = Registration.objects.create(tournament=self.tournament, player=self.player, checked_in=True)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/registrations/{registration.pk}/review/',
            {'status': 'rejected', 'reason': "Payment screenshot doesn't match the entry fee."},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.REJECTED)
        self.assertEqual(registration.rejection_reason, "Payment screenshot doesn't match the entry fee.")
        self.assertFalse(registration.checked_in)
        self.assertIsNone(registration.checked_in_at)


class AnnouncementApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        self.organizer_user = User.objects.create_user(email='ann-organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Acme Esports')
        self.other_organizer_user = User.objects.create_user(email='ann-other-organizer@example.com', password='StrongPass123')
        Organizer.objects.create(user=self.other_organizer_user, company_name='Other Co')
        self.admin = User.objects.create_user(email='ann-admin@example.com', password='StrongPass123', is_staff=True)
        self.player = User.objects.create_user(email='ann-player@example.com', password='StrongPass123')
        self.tournament = Tournament.objects.create(
            name='Winter Cup', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
            status=Tournament.Status.APPROVED, is_published=True,
        )

    def _post(self, user, **payload):
        self.client.force_authenticate(user=user)
        return self.client.post(f'/api/tournaments/{self.tournament.pk}/announcements/', {
            'category': 'delay', 'title': 'Round 1 delayed', 'message': 'Pushed back 30 minutes.', **payload,
        })

    def test_post_requires_auth(self):
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/announcements/', {
            'category': 'delay', 'title': 'x', 'message': 'y',
        })
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_player_cannot_post(self):
        resp = self._post(self.player)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_organizer_cannot_post(self):
        resp = self._post(self.other_organizer_user)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owning_organizer_can_post(self):
        resp = self._post(self.organizer_user)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['category'], 'delay')
        self.assertEqual(resp.data['category_display'], 'Delay')
        self.assertEqual(resp.data['author_name'], self.organizer_user.email)
        self.assertTrue(Announcement.objects.filter(tournament=self.tournament).exists())

    def test_admin_can_post(self):
        resp = self._post(self.admin)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_player_can_list(self):
        Announcement.objects.create(
            tournament=self.tournament, author=self.organizer_user,
            category=Announcement.Category.VENUE_UPDATE, title='New venue', message='Moved to Hall B.',
        )
        self.client.force_authenticate(user=self.player)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/announcements/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['title'], 'New venue')

    def test_player_cannot_delete(self):
        announcement = Announcement.objects.create(
            tournament=self.tournament, author=self.organizer_user, title='x', message='y',
        )
        self.client.force_authenticate(user=self.player)
        resp = self.client.delete(f'/api/announcements/{announcement.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owning_organizer_can_delete(self):
        announcement = Announcement.objects.create(
            tournament=self.tournament, author=self.organizer_user, title='x', message='y',
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.delete(f'/api/announcements/{announcement.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Announcement.objects.filter(pk=announcement.pk).exists())


class TournamentApplicationValidationTests(TestCase):
    """Direct serializer tests for the validation added to TournamentApplicationSerializer —
    unit-style (no HTTP layer) since .is_valid() alone never triggers a Cloudinary
    upload for the required document fields, only .save() would."""

    def setUp(self):
        self.game = Game.objects.create(name='Validation Test Game', genre='FPS')

    def _payload(self, **overrides):
        payload = {
            'name': 'Test Cup',
            'game': self.game.pk,
            'mode': Tournament.Mode.ONLINE,
            'bracket_format': Tournament.BracketFormat.SINGLE,
            'team_size': 1,
            'registration_fee': '0',
            'prize_pool': '0',
            'starts_at': timezone.now() + timedelta(days=7),
            'platform': 'PC',
            'company_registration_certificate': SimpleUploadedFile(
                'doc.pdf', _PDF_BYTES, content_type='application/pdf',
            ),
            'organizer_cnic_front': SimpleUploadedFile('front.pdf', _PDF_BYTES, content_type='application/pdf'),
            'organizer_cnic_back': SimpleUploadedFile('back.pdf', _PDF_BYTES, content_type='application/pdf'),
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_accepted(self):
        serializer = TournamentApplicationSerializer(data=self._payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_negative_registration_fee_rejected(self):
        serializer = TournamentApplicationSerializer(data=self._payload(registration_fee='-500'))
        self.assertFalse(serializer.is_valid())
        self.assertIn('registration_fee', serializer.errors)

    def test_negative_prize_pool_rejected(self):
        serializer = TournamentApplicationSerializer(data=self._payload(prize_pool='-1'))
        self.assertFalse(serializer.is_valid())
        self.assertIn('prize_pool', serializer.errors)

    def test_starts_at_in_past_rejected(self):
        serializer = TournamentApplicationSerializer(
            data=self._payload(starts_at=timezone.now() - timedelta(days=1)),
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('starts_at', serializer.errors)

    def test_registration_deadline_in_past_rejected(self):
        serializer = TournamentApplicationSerializer(
            data=self._payload(registration_deadline=timezone.now() - timedelta(days=1)),
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('registration_deadline', serializer.errors)

    def test_zero_team_size_rejected(self):
        serializer = TournamentApplicationSerializer(data=self._payload(team_size=0))
        self.assertFalse(serializer.is_valid())
        self.assertIn('team_size', serializer.errors)

    def test_zero_max_participants_rejected(self):
        serializer = TournamentApplicationSerializer(data=self._payload(max_participants=0))
        self.assertFalse(serializer.is_valid())
        self.assertIn('max_participants', serializer.errors)

    def test_invalid_contact_phone_rejected(self):
        serializer = TournamentApplicationSerializer(data=self._payload(contact_phone='abc'))
        self.assertFalse(serializer.is_valid())
        self.assertIn('contact_phone', serializer.errors)

    def test_valid_contact_phone_accepted(self):
        serializer = TournamentApplicationSerializer(data=self._payload(contact_phone='+923001234567'))
        self.assertTrue(serializer.is_valid(), serializer.errors)


class TeamApiTests(APITestCase):
    def setUp(self):
        self.game = Game.objects.create(name='Team Game', genre='MOBA')
        self.organizer_user = User.objects.create_user(email='team-organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Team Co')
        self.tournament = Tournament.objects.create(
            name='Team Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now(), team_size=2, status=Tournament.Status.APPROVED,
        )
        self.captain = User.objects.create_user(email='captain@example.com', password='StrongPass123')
        self.joiner = User.objects.create_user(email='joiner@example.com', password='StrongPass123')
        self.other_joiner = User.objects.create_user(email='other-joiner@example.com', password='StrongPass123')

    def test_create_team(self):
        self.client.force_authenticate(user=self.captain)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/', {'name': 'Alpha'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['name'], 'Alpha')
        self.assertEqual(len(resp.data['members']), 1)

    def test_create_team_duplicate_name_rejected_cleanly(self):
        Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        self.client.force_authenticate(user=self.joiner)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/', {'name': 'Alpha'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_team(self):
        team = Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=self.captain)

        self.client.force_authenticate(user=self.joiner)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/join/', {'invite_code': team.invite_code})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(len(resp.data['members']), 2)

    def test_join_full_team_rejected(self):
        team = Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=self.captain)
        TeamMembership.objects.create(team=team, player=self.joiner)  # team_size=2, now full

        self.client.force_authenticate(user=self.other_joiner)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/join/', {'invite_code': team.invite_code})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_invalid_code_rejected(self):
        self.client.force_authenticate(user=self.joiner)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/join/', {'invite_code': 'NOTREAL1'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_full_team(self):
        team = Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=self.captain)
        TeamMembership.objects.create(team=team, player=self.joiner)

        self.client.force_authenticate(user=self.captain)
        resp = self.client.post(f'/api/teams/{team.pk}/register/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(Registration.objects.filter(tournament=self.tournament, team=team).exists())

    def test_register_team_twice_rejected_cleanly(self):
        team = Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=self.captain)
        TeamMembership.objects.create(team=team, player=self.joiner)
        Registration.objects.create(tournament=self.tournament, player=self.captain, team=team)

        self.client.force_authenticate(user=self.captain)
        resp = self.client.post(f'/api/teams/{team.pk}/register/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
