import threading
from datetime import timedelta

import fitz
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from core.models import AdminReviewRequest, AuditLog
from games.models import Game
from organizer.models import Organizer
from tourny_regist import lifecycle
from tourny_regist.models import Announcement, Registration, Team, TeamMembership, Tournament, TournamentRuleVersion
from tourny_regist.serializers import TournamentApplicationSerializer, TournamentUpdateSerializer

User = get_user_model()


def _make_pdf_bytes():
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


# Genuinely decodable, not just correct magic bytes — validate_document_file
# (core/validators.py) actually opens this with PyMuPDF, not just sniffs the header.
_PDF_BYTES = _make_pdf_bytes()


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
            status=Tournament.Status.APPROVED,
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

    def test_cannot_hard_delete_a_registration_once_a_bracket_exists(self):
        # Business-logic regression test: this endpoint previously had no
        # state guard at all — a player could hard-delete their own
        # registration after being seeded (or even after winning a match)
        # into a live bracket, orphaning the opponent's match with no
        # forfeit recorded, and immediately re-register with a clean row.
        from brackets.models import Bracket

        registration = Registration.objects.create(tournament=self.tournament, player=self.player, checked_in=True)
        Bracket.objects.create(tournament=self.tournament, format=Bracket.Format.SINGLE, total_rounds=1)

        resp = self.client.delete(f'/api/registrations/{registration.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Registration.objects.filter(pk=registration.pk).exists())

        # Not even staff can bypass this via the same endpoint — the
        # deliberate paths for removing a bracket-era registration
        # (disqualify_registration/cancel_registration) are what know how
        # to unwind a live match cleanly.
        self.client.force_authenticate(user=self.admin)
        admin_resp = self.client.delete(f'/api/registrations/{registration.pk}/')
        self.assertEqual(admin_resp.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_checkin_status_frozen_once_a_bracket_exists(self):
        # Business-logic regression test: brackets.services.standings()/
        # generate_next_swiss_round() re-derive the eligible player pool
        # live from whichever registrations are *currently* checked_in, not
        # a roster frozen at bracket-generation time. Without this guard, a
        # late check-in after a bracket exists injects a player who never
        # played earlier rounds into a later one; an un-check-in silently
        # drops a player with a completed, won match and no forfeit.
        from brackets.models import Bracket

        checked_in_reg = Registration.objects.create(
            tournament=self.tournament, player=self.player, checked_in=True,
        )
        not_yet_checked_in_reg = Registration.objects.create(tournament=self.tournament, player=self.other_player)
        Bracket.objects.create(tournament=self.tournament, format=Bracket.Format.SINGLE, total_rounds=1)

        self.client.force_authenticate(user=self.organizer_user)
        undo_resp = self.client.patch(
            f'/api/registrations/{checked_in_reg.pk}/check-in/', {'checked_in': False},
        )
        self.assertEqual(undo_resp.status_code, status.HTTP_400_BAD_REQUEST)
        checked_in_reg.refresh_from_db()
        self.assertTrue(checked_in_reg.checked_in)

        late_checkin_resp = self.client.patch(f'/api/registrations/{not_yet_checked_in_reg.pk}/check-in/')
        self.assertEqual(late_checkin_resp.status_code, status.HTTP_400_BAD_REQUEST)
        not_yet_checked_in_reg.refresh_from_db()
        self.assertFalse(not_yet_checked_in_reg.checked_in)

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

    def test_disqualified_registration_cannot_be_checked_in_on_a_free_tournament(self):
        # Business-logic regression test: the registration_fee > 0 gate that
        # would otherwise require status == APPROVED never runs at all for a
        # free tournament (self.tournament here has the default fee, 0) —
        # DISQUALIFIED/CANCELLED weren't in the terminal-status blocklist
        # (only REJECTED was), so a disqualified player — already forfeited
        # out of their bracket match — could be checked back in as if
        # nothing had happened.
        self.assertEqual(self.tournament.registration_fee, 0)
        registration = Registration.objects.create(
            tournament=self.tournament, player=self.player, status=Registration.Status.DISQUALIFIED,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/registrations/{registration.pk}/check-in/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        registration.refresh_from_db()
        self.assertFalse(registration.checked_in)

    def test_cancelled_registration_cannot_be_checked_in_on_a_free_tournament(self):
        registration = Registration.objects.create(
            tournament=self.tournament, player=self.player, status=Registration.Status.CANCELLED,
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

    def test_cannot_review_a_disqualified_registration(self):
        # Business-logic regression test: RegistrationReviewSerializer had no
        # whitelist of valid status transitions at all — a plain PATCH
        # {"status": "approved"} could silently reinstate a DISQUALIFIED
        # registration (reached only via lifecycle.disqualify_registration,
        # which forfeits a live match as a side effect) with no reason
        # required and no link back to why it was disqualified in the first
        # place, undoing that forfeit's implications without undoing the
        # forfeit itself.
        registration = Registration.objects.create(
            tournament=self.tournament, player=self.player, status=Registration.Status.DISQUALIFIED,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/registrations/{registration.pk}/review/', {'status': 'approved'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.DISQUALIFIED)

    def test_cannot_review_a_cancelled_registration(self):
        registration = Registration.objects.create(
            tournament=self.tournament, player=self.player, status=Registration.Status.CANCELLED,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(
            f'/api/registrations/{registration.pk}/review/', {'status': 'approved'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RegistrationCapacityConcurrencyTests(TransactionTestCase):
    """Real threads against a real database — the row-lock behaviour in
    RegistrationCreateView (a select_for_update on the Tournament row, added
    alongside this test) cannot be exercised inside a single wrapped
    transaction. Mirrors brackets/tests.py:MatchCompletionConcurrencyTests."""

    def setUp(self):
        self.game = Game.objects.create(name='Valorant', genre='FPS')
        organizer_user = User.objects.create_user(email='regconc-org@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=organizer_user, company_name='RegConc Co')
        self.tournament = Tournament.objects.create(
            name='Capacity Cup', game=self.game, organizer=self.organizer,
            status=Tournament.Status.APPROVED, max_participants=1, starts_at=timezone.now(),
        )
        self.players = [
            User.objects.create_user(email=f'regconc-p{i}@example.com', password='StrongPass123') for i in range(2)
        ]

    def _payload(self):
        return {
            'tournament': self.tournament.pk,
            'full_name': 'Test Player', 'gaming_username': 'TestTag', 'phone_number': '+923001234567',
            'contact_email': 'player@example.com', 'country': 'Pakistan', 'city': 'Lahore',
            'platform': 'Steam', 'platform_username': 'testplayer',
            'accepted_rules': True, 'accepted_code_of_conduct': True,
        }

    def test_simultaneous_registrations_do_not_exceed_max_participants(self):
        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()

        def attempt(player):
            client = APIClient()
            client.force_authenticate(user=player)
            try:
                barrier.wait(timeout=10)
                resp = client.post('/api/registrations/', self._payload())
                with lock:
                    outcomes.append(resp.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(p,)) for p in self.players]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        self.assertEqual(
            sorted(outcomes), [201, 400],
            f'exactly one registration should succeed once max_participants=1 is reached, got {outcomes}',
        )
        self.assertEqual(Registration.objects.filter(tournament=self.tournament).count(), 1)


class TeamMembershipConcurrencyTests(TransactionTestCase):
    """Real threads against a real database. Regression test for a race
    found during a business-logic audit: TeamCreateView and TeamJoinView
    each used to lock only the *team* row they were touching (a new team
    doesn't exist yet to lock, an existing team's own row for joining) —
    neither serialized against the other, so the same player could create
    one team and join a different one at the same instant, ending up on two
    rosters in one tournament. Both now lock the Tournament row instead."""

    def setUp(self):
        self.game = Game.objects.create(name='Concurrency Game', genre='MOBA')
        organizer_user = User.objects.create_user(email='teamconc-org@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=organizer_user, company_name='TeamConc Co')
        self.tournament = Tournament.objects.create(
            name='Team Race Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now(), team_size=2, status=Tournament.Status.APPROVED,
        )
        self.captain = User.objects.create_user(email='teamconc-captain@example.com', password='StrongPass123')
        self.player = User.objects.create_user(email='teamconc-player@example.com', password='StrongPass123')

    def test_creating_a_team_and_joining_another_at_the_same_instant_only_one_succeeds(self):
        existing_team = Team.objects.create(tournament=self.tournament, name='Existing', captain=self.captain)
        TeamMembership.objects.create(team=existing_team, player=self.captain)

        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()

        def create_new_team():
            client = APIClient()
            client.force_authenticate(user=self.player)
            try:
                barrier.wait(timeout=10)
                resp = client.post(f'/api/tournaments/{self.tournament.pk}/teams/', {'name': 'New Team'})
                with lock:
                    outcomes.append(('create', resp.status_code))
            finally:
                connection.close()

        def join_existing_team():
            client = APIClient()
            client.force_authenticate(user=self.player)
            try:
                barrier.wait(timeout=10)
                resp = client.post(
                    f'/api/tournaments/{self.tournament.pk}/teams/join/',
                    {'invite_code': existing_team.invite_code},
                )
                with lock:
                    outcomes.append(('join', resp.status_code))
            finally:
                connection.close()

        threads = [threading.Thread(target=create_new_team), threading.Thread(target=join_existing_team)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        statuses = sorted(code for _, code in outcomes)
        self.assertEqual(
            statuses, [201, 400],
            f'exactly one of create-team/join-team should succeed for the same player, got {outcomes}',
        )
        self.assertEqual(
            TeamMembership.objects.filter(team__tournament=self.tournament, player=self.player).count(), 1,
        )


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
        # display_name() never falls back to a real email — announcements are
        # visible to any authenticated user, not just this tournament's stakeholders.
        self.assertEqual(resp.data['author_name'], f'User #{self.organizer_user.pk}')
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

    def test_outsider_cannot_list_announcements_for_an_unpublished_tournament(self):
        # Regression test: GET previously only required IsAuthenticated (any
        # account), not a stakeholder in *this* tournament — a client could
        # list announcements for a draft/pending/unpublished tournament ID it
        # had no relationship to just by guessing it.
        unpublished = Tournament.objects.create(
            name='Not Announced Yet', game=self.game, organizer=self.organizer, starts_at=timezone.now(),
            status=Tournament.Status.APPROVED, is_published=False, created_by=self.organizer_user,
        )
        Announcement.objects.create(
            tournament=unpublished, author=self.organizer_user,
            category=Announcement.Category.GENERAL, title='Internal note', message='Not public yet.',
        )
        self.client.force_authenticate(user=self.player)
        resp = self.client.get(f'/api/tournaments/{unpublished.pk}/announcements/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.organizer_user)
        owner_resp = self.client.get(f'/api/tournaments/{unpublished.pk}/announcements/')
        self.assertEqual(owner_resp.status_code, status.HTTP_200_OK)

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


class TournamentUpdateValidationTests(TestCase):
    """TournamentUpdateSerializer must reject moving starts_at/registration_deadline
    to a new past value, but must NOT reject a save that leaves an already-past
    date untouched — the edit form resends the full payload (including unchanged
    dates) on every save, so a blanket 'must be in the future' check would lock
    organizers out of editing any tournament that has already started."""

    def setUp(self):
        self.game = Game.objects.create(name='Update Validation Game', genre='FPS')
        self.organizer_user = User.objects.create_user(email='update-organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.organizer_user, company_name='Update Co')

    def _base_fields(self, tournament):
        return {
            'name': tournament.name,
            'game': tournament.game_id,
            'mode': tournament.mode,
            'bracket_format': tournament.bracket_format,
            'team_size': tournament.team_size,
            'registration_fee': str(tournament.registration_fee),
            'prize_pool': str(tournament.prize_pool),
            'starts_at': tournament.starts_at,
            'registration_deadline': tournament.registration_deadline,
            'platform': tournament.platform or 'PC',
        }

    def test_moving_starts_at_into_the_past_rejected(self):
        tournament = Tournament.objects.create(
            name='Future Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now() + timedelta(days=7),
        )
        payload = self._base_fields(tournament)
        payload['starts_at'] = timezone.now() - timedelta(days=1)
        serializer = TournamentUpdateSerializer(instance=tournament, data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('starts_at', serializer.errors)

    def test_saving_unchanged_past_starts_at_accepted(self):
        already_started = timezone.now() - timedelta(days=1)
        tournament = Tournament.objects.create(
            name='Live Cup', game=self.game, organizer=self.organizer,
            starts_at=already_started,
        )
        payload = self._base_fields(tournament)
        payload['prize_pool'] = '500'
        serializer = TournamentUpdateSerializer(instance=tournament, data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_moving_registration_deadline_into_the_past_rejected(self):
        tournament = Tournament.objects.create(
            name='Deadline Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now() + timedelta(days=7),
            registration_deadline=timezone.now() + timedelta(days=3),
        )
        payload = self._base_fields(tournament)
        payload['registration_deadline'] = timezone.now() - timedelta(days=1)
        serializer = TournamentUpdateSerializer(instance=tournament, data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('registration_deadline', serializer.errors)

    def test_team_size_cannot_change_once_a_team_has_registered(self):
        # Business-logic regression test: TournamentUpdateSerializer had no
        # check tying team_size/bracket_format/game to whether anyone had
        # already signed up — raising team_size after a team registered
        # (with exactly the old team_size) reopened TeamJoinView's capacity
        # check, letting a new player join an *already-registered* roster
        # the organizer had already submitted.
        from tourny_regist.models import Registration, Team

        tournament = Tournament.objects.create(
            name='Roster Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now() + timedelta(days=7), team_size=2, status=Tournament.Status.APPROVED,
        )
        captain = User.objects.create_user(email='roster-captain@example.com', password='StrongPass123')
        teammate = User.objects.create_user(email='roster-teammate@example.com', password='StrongPass123')
        team = Team.objects.create(tournament=tournament, name='Locked In', captain=captain)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=captain)
        TeamMembership.objects.create(team=team, player=teammate)
        Registration.objects.create(tournament=tournament, player=captain, team=team)

        payload = self._base_fields(tournament)
        payload['team_size'] = 3
        serializer = TournamentUpdateSerializer(instance=tournament, data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('team_size', serializer.errors)

    def test_team_size_editable_before_anyone_has_registered(self):
        tournament = Tournament.objects.create(
            name='Still Draft Cup', game=self.game, organizer=self.organizer,
            starts_at=timezone.now() + timedelta(days=7), team_size=2,
        )
        payload = self._base_fields(tournament)
        payload['team_size'] = 4
        serializer = TournamentUpdateSerializer(instance=tournament, data=payload)
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


class LifecycleTestBase(APITestCase):
    """Shared fixtures for the tournament-lifecycle test classes below —
    two organizers (so cross-organizer/IDOR checks have a real "other" to
    target), an admin, and a player."""

    def setUp(self):
        self.game = Game.objects.create(name='Lifecycle Game', genre='FPS')

        self.organizer_user = User.objects.create_user(email='lc-organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(
            user=self.organizer_user, company_name='LC Co', status=Organizer.Status.APPROVED,
        )

        self.other_organizer_user = User.objects.create_user(email='lc-other-organizer@example.com', password='StrongPass123')
        self.other_organizer = Organizer.objects.create(
            user=self.other_organizer_user, company_name='LC Other Co', status=Organizer.Status.APPROVED,
        )

        self.admin = User.objects.create_user(email='lc-admin@example.com', password='StrongPass123', is_staff=True)
        self.player = User.objects.create_user(email='lc-player@example.com', password='StrongPass123')

    def _draft(self, **overrides):
        defaults = {'name': 'Draft Cup', 'game': self.game, 'organizer': self.organizer, 'status': Tournament.Status.DRAFT}
        defaults.update(overrides)
        return Tournament.objects.create(**defaults)

    def _full_draft_payload(self):
        """Everything submit_tournament requires, minus the three documents."""
        return {
            'mode': Tournament.Mode.ONLINE,
            'platform': 'PC',
            'starts_at': timezone.now() + timedelta(days=7),
        }


class TournamentDraftTests(LifecycleTestBase):
    def test_create_draft_with_minimal_fields(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post('/api/tournaments/drafts/', {'name': 'My Draft', 'game': self.game.pk})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], Tournament.Status.DRAFT)
        self.assertFalse(resp.data['is_published'])

    def test_create_draft_requires_approved_organizer(self):
        unapproved_user = User.objects.create_user(email='lc-unapproved@example.com', password='StrongPass123')
        Organizer.objects.create(user=unapproved_user, company_name='Unapproved Co', status=Organizer.Status.PENDING)
        self.client.force_authenticate(user=unapproved_user)
        resp = self.client.post('/api/tournaments/drafts/', {'name': 'My Draft', 'game': self.game.pk})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_edit_draft_does_not_require_venue_or_platform(self):
        draft = self._draft()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/tournaments/{draft.pk}/', {'mode': Tournament.Mode.OFFLINE}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_submit_incomplete_draft_rejected(self):
        draft = self._draft()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{draft.pk}/submit/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('starts_at', resp.data)

    def test_submit_complete_draft_succeeds(self):
        draft = self._draft(
            mode=Tournament.Mode.ONLINE, platform='PC', starts_at=timezone.now() + timedelta(days=7),
            company_registration_certificate=SimpleUploadedFile('a.pdf', _PDF_BYTES, content_type='application/pdf'),
            organizer_cnic_front=SimpleUploadedFile('b.pdf', _PDF_BYTES, content_type='application/pdf'),
            organizer_cnic_back=SimpleUploadedFile('c.pdf', _PDF_BYTES, content_type='application/pdf'),
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{draft.pk}/submit/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], Tournament.Status.PENDING)

    def test_submit_only_from_draft(self):
        tournament = self._draft(status=Tournament.Status.PENDING)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/submit/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_cross_organizer_forbidden(self):
        draft = self._draft()
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{draft.pk}/submit/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_register_against_a_draft(self):
        draft = self._draft(is_registration_open=True)
        self.client.force_authenticate(user=self.player)
        resp = self.client.post('/api/registrations/', {
            'tournament': draft.pk, 'full_name': 'P', 'gaming_username': 'P', 'phone_number': '+923001234567',
            'contact_email': 'p@example.com', 'country': 'PK', 'city': 'Lahore',
            'accepted_rules': True, 'accepted_code_of_conduct': True, 'platform': 'PC', 'platform_username': 'p',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TournamentResubmitTests(LifecycleTestBase):
    def test_resubmit_from_rejected(self):
        tournament = self._draft(status=Tournament.Status.REJECTED, rejection_reason='bad docs')
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], Tournament.Status.PENDING)
        self.assertEqual(resp.data['rejection_reason'], '')

    def test_resubmit_only_from_rejected(self):
        tournament = self._draft(status=Tournament.Status.PENDING)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resubmit_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.REJECTED)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TournamentCancellationTests(LifecycleTestBase):
    def test_safe_cancel_is_immediate(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'Venue fell through'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], Tournament.Status.CANCELLED)
        tournament.refresh_from_db()
        self.assertEqual(tournament.cancelled_by_id, self.organizer_user.pk)
        self.assertIsNotNone(tournament.cancelled_at)
        self.assertFalse(tournament.is_published)
        self.assertFalse(tournament.is_registration_open)

    def test_cancel_requires_reason(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': ''})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_already_cancelled_rejected(self):
        tournament = self._draft(status=Tournament.Status.CANCELLED)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'again'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'not mine'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_with_registrations_requires_admin_review(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'Too few players'})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED, resp.data)
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, Tournament.Status.APPROVED)  # unchanged
        review_request = AdminReviewRequest.objects.get(object_id=tournament.pk)
        self.assertEqual(review_request.status, AdminReviewRequest.Status.PENDING)
        self.assertEqual(review_request.request_type, AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION)

    def test_repeated_cancel_clicks_do_not_queue_duplicate_review_requests(self):
        # Business-logic regression test: a retried/double-clicked cancel
        # request used to create a fresh AdminReviewRequest every time
        # (NeedsAdminReview is re-raised identically each call, since the
        # tournament's own state hasn't changed) — AdminReviewRequest.Meta's
        # partial UniqueConstraint (only one PENDING per target+type) plus
        # the view catching IntegrityError now makes a retry a clean no-op
        # 202 instead of a queue of duplicates for an admin to work through.
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)

        first = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'Too few players'})
        second = self.client.post(f'/api/tournaments/{tournament.pk}/cancel/', {'reason': 'Still too few'})
        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            AdminReviewRequest.objects.filter(
                object_id=tournament.pk, request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            ).count(),
            1,
        )

    def test_admin_approving_review_request_cancels_tournament(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            reason='Too few players', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'approved', 'reason': 'ok'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, Tournament.Status.CANCELLED)

    def test_admin_rejecting_review_request_leaves_tournament_untouched(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            reason='Too few players', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'rejected', 'reason': 'no'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, Tournament.Status.APPROVED)

    def test_non_staff_cannot_decide_review_request(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            reason='x', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_double_decide_rejected(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            reason='x', content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
            status=AdminReviewRequest.Status.APPROVED, decided_by=self.admin, decided_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'rejected'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_request_list_staff_only(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get('/api/admin/review-requests/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TournamentRescheduleTests(LifecycleTestBase):
    def test_reschedule_success(self):
        old_starts_at = timezone.now() + timedelta(days=7)
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=old_starts_at)
        self.client.force_authenticate(user=self.organizer_user)
        new_starts_at = timezone.now() + timedelta(days=14)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/reschedule/', {
            'reason': 'Venue conflict', 'starts_at': new_starts_at.isoformat(),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        tournament.refresh_from_db()
        self.assertAlmostEqual(tournament.starts_at, new_starts_at, delta=timedelta(seconds=1))

    def test_reschedule_past_date_rejected(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7))
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/reschedule/', {
            'reason': 'x', 'starts_at': (timezone.now() - timedelta(days=1)).isoformat(),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reschedule_invalid_ordering_rejected(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7))
        self.client.force_authenticate(user=self.organizer_user)
        new_starts_at = timezone.now() + timedelta(days=14)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/reschedule/', {
            'reason': 'x', 'starts_at': new_starts_at.isoformat(),
            'ends_at': (new_starts_at - timedelta(days=1)).isoformat(),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reschedule_requires_reason(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7))
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/reschedule/', {
            'reason': '', 'starts_at': (timezone.now() + timedelta(days=14)).isoformat(),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reschedule_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7))
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/reschedule/', {
            'reason': 'x', 'starts_at': (timezone.now() + timedelta(days=14)).isoformat(),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TournamentDuplicateTests(LifecycleTestBase):
    def test_duplicate_copies_config_not_competitive_data(self):
        tournament = self._draft(
            status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7),
            mode=Tournament.Mode.ONLINE, platform='PC', prize_pool='500',
        )
        Registration.objects.create(tournament=tournament, player=self.player)

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/duplicate/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        new_tournament = Tournament.objects.get(pk=resp.data['id'])
        self.assertEqual(new_tournament.status, Tournament.Status.DRAFT)
        self.assertFalse(new_tournament.is_published)
        self.assertEqual(new_tournament.platform, 'PC')
        self.assertEqual(str(new_tournament.prize_pool), '500.00')
        self.assertEqual(new_tournament.registrations.count(), 0)
        self.assertFalse(hasattr(new_tournament, 'bracket'))

    def test_duplicate_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/duplicate/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_allowed_for_staff(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/duplicate/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class ServiceLayerInvariantTests(LifecycleTestBase):
    """Calls tourny_regist.lifecycle functions directly, bypassing the view
    layer entirely — proves the *service function itself* enforces its
    safety invariant, not just "the one view that currently calls it happens
    to check first." Matters specifically because AdminReviewRequest
    approval re-invokes these same functions (see lifecycle.py's module
    docstring / SECURITY.md#admin-review-escalation) — a future call site
    (a bulk-admin action, a management command, a Celery task) that calls
    cancel_tournament directly must get the same protection a normal request
    would, without having to remember to re-implement the check itself."""

    def test_cancel_tournament_raises_needs_admin_review_when_called_directly_with_registrations(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player, checked_in=True)

        with self.assertRaises(lifecycle.NeedsAdminReview):
            lifecycle.cancel_tournament(tournament, self.organizer_user, 'Testing')

        tournament.refresh_from_db()
        self.assertNotEqual(tournament.status, Tournament.Status.CANCELLED)

    def test_cancel_tournament_bypass_safety_check_only_works_after_the_flag_is_explicit(self):
        # The same call that raised NeedsAdminReview above succeeds once
        # bypass_safety_check=True is passed explicitly — the exact
        # transition AdminReviewRequest approval performs — but never as a
        # side effect of anything else.
        tournament = self._draft(status=Tournament.Status.APPROVED)
        Registration.objects.create(tournament=tournament, player=self.player, checked_in=True)

        result = lifecycle.cancel_tournament(tournament, self.admin, 'Approved by admin', bypass_safety_check=True)
        self.assertEqual(result.status, Tournament.Status.CANCELLED)


class AuditLogTests(LifecycleTestBase):
    def test_cancel_creates_audit_log(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        lifecycle.cancel_tournament(tournament, self.organizer_user, 'Testing')
        entry = AuditLog.objects.get(action='tournament.cancelled', object_id=tournament.pk)
        self.assertEqual(entry.actor_id, self.organizer_user.pk)
        self.assertEqual(entry.reason, 'Testing')

    def test_reschedule_creates_audit_log_with_old_and_new_dates(self):
        old_starts_at = timezone.now() + timedelta(days=7)
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=old_starts_at)
        new_starts_at = timezone.now() + timedelta(days=14)
        lifecycle.reschedule_tournament(tournament, self.organizer_user, 'Testing', new_starts_at)
        entry = AuditLog.objects.get(action='tournament.rescheduled', object_id=tournament.pk)
        self.assertIn('old', entry.metadata)
        self.assertIn('new', entry.metadata)
        self.assertEqual(entry.metadata['new']['starts_at'], new_starts_at.isoformat())

    def test_duplicate_creates_audit_log_referencing_source(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        new_tournament = lifecycle.duplicate_tournament(tournament, self.organizer_user)
        entry = AuditLog.objects.get(action='tournament.duplicated', object_id=new_tournament.pk)
        self.assertEqual(entry.metadata['source_tournament_id'], tournament.pk)


class AdminTournamentDecisionTests(LifecycleTestBase):
    """AdminTournamentUpdateSerializer.validate_status must only allow
    PENDING -> APPROVED/REJECTED — DRAFT and CANCELLED have their own
    dedicated workflows and must not be reachable via this generic PATCH."""

    def test_admin_can_still_approve_a_pending_tournament(self):
        tournament = self._draft(status=Tournament.Status.PENDING, starts_at=timezone.now() + timedelta(days=7))
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/tournaments/{tournament.pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, Tournament.Status.APPROVED)

    def test_admin_cannot_approve_a_draft_directly(self):
        draft = self._draft()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/tournaments/{draft.pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Tournament.Status.DRAFT)

    def test_admin_cannot_revive_a_cancelled_tournament(self):
        tournament = self._draft(status=Tournament.Status.CANCELLED)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/tournaments/{tournament.pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, Tournament.Status.CANCELLED)


class RegistrationStatusGapTests(LifecycleTestBase):
    """A PENDING/REJECTED tournament isn't publicly listed, but its id is
    guessable — registration endpoints must reject it directly, not rely on
    obscurity. See tourny_regist.serializers.RegistrationCreateSerializer and
    tourny_regist.views.TeamRegisterView."""

    def test_solo_register_against_pending_tournament_rejected(self):
        tournament = self._draft(status=Tournament.Status.PENDING)
        self.client.force_authenticate(user=self.player)
        resp = self.client.post('/api/registrations/', {
            'tournament': tournament.pk, 'full_name': 'P', 'gaming_username': 'P', 'phone_number': '+923001234567',
            'contact_email': 'p@example.com', 'country': 'PK', 'city': 'Lahore',
            'accepted_rules': True, 'accepted_code_of_conduct': True, 'platform': 'PC', 'platform_username': 'p',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_solo_register_against_rejected_tournament_rejected(self):
        tournament = self._draft(status=Tournament.Status.REJECTED)
        self.client.force_authenticate(user=self.player)
        resp = self.client.post('/api/registrations/', {
            'tournament': tournament.pk, 'full_name': 'P', 'gaming_username': 'P', 'phone_number': '+923001234567',
            'contact_email': 'p@example.com', 'country': 'PK', 'city': 'Lahore',
            'accepted_rules': True, 'accepted_code_of_conduct': True, 'platform': 'PC', 'platform_username': 'p',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_team_register_against_pending_tournament_rejected(self):
        tournament = self._draft(status=Tournament.Status.PENDING, team_size=1)
        team = Team.objects.create(tournament=tournament, name='Alpha', captain=self.player)
        from tourny_regist.models import TeamMembership
        TeamMembership.objects.create(team=team, player=self.player)

        self.client.force_authenticate(user=self.player)
        resp = self.client.post(f'/api/teams/{team.pk}/register/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RegistrationCancellationTests(LifecycleTestBase):
    def setUp(self):
        super().setUp()
        self.other_player = User.objects.create_user(email='lc-other-player@example.com', password='StrongPass123')

    def _approved_tournament_with_registration(self, player=None):
        player = player or self.player
        tournament = self._draft(status=Tournament.Status.APPROVED, starts_at=timezone.now() + timedelta(days=7))
        registration = Registration.objects.create(tournament=tournament, player=player)
        return tournament, registration

    def _completed_match_for(self, tournament, player, opponent):
        from brackets.models import Bracket, Match
        bracket = Bracket.objects.create(tournament=tournament, format=Bracket.Format.SINGLE, total_rounds=1)
        Match.objects.create(
            bracket=bracket, tournament=tournament, round_number=1, position=1,
            player1=player, player2=opponent, winner=player, status=Match.Status.COMPLETED,
        )

    def test_safe_cancel_is_immediate(self):
        tournament, registration = self._approved_tournament_with_registration()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': 'No longer eligible'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], Registration.Status.CANCELLED)
        registration.refresh_from_db()
        self.assertEqual(registration.cancelled_by_id, self.organizer_user.pk)
        self.assertFalse(registration.checked_in)

    def test_cancel_requires_reason(self):
        tournament, registration = self._approved_tournament_with_registration()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': ''})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_cross_organizer_forbidden(self):
        tournament, registration = self._approved_tournament_with_registration()
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': 'not mine'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_before_bracket_exists_is_safe(self):
        tournament, registration = self._approved_tournament_with_registration()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_already_cancelled_registration_cannot_be_cancelled_again(self):
        tournament, registration = self._approved_tournament_with_registration()
        registration.status = Registration.Status.CANCELLED
        registration.save()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_after_playing_a_match_requires_admin_review(self):
        tournament, registration = self._approved_tournament_with_registration()
        Registration.objects.create(tournament=tournament, player=self.other_player)
        self._completed_match_for(tournament, self.player, self.other_player)

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/cancel/', {'reason': 'no longer eligible'})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED, resp.data)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.APPROVED)
        review_request = AdminReviewRequest.objects.get(
            object_id=registration.pk, request_type=AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION,
        )
        self.assertEqual(review_request.status, AdminReviewRequest.Status.PENDING)

    def test_admin_approving_review_request_cancels_registration(self):
        tournament, registration = self._approved_tournament_with_registration()
        Registration.objects.create(tournament=tournament, player=self.other_player)
        self._completed_match_for(tournament, self.player, self.other_player)

        review_request = AdminReviewRequest.objects.create(
            requested_by=self.organizer_user, request_type=AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION,
            reason='x', content_type=ContentType.objects.get_for_model(Registration), object_id=registration.pk,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/admin/review-requests/{review_request.pk}/decide/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)


class RegistrationFilterExportTests(LifecycleTestBase):
    def setUp(self):
        super().setUp()
        self.tournament = self._draft(status=Tournament.Status.APPROVED)
        self.reg1 = Registration.objects.create(
            tournament=self.tournament, player=self.player, full_name='Alice Smith', gaming_username='AliceGG',
        )
        other = User.objects.create_user(email='lc-bob@example.com', password='StrongPass123')
        self.reg2 = Registration.objects.create(
            tournament=self.tournament, player=other, full_name='Bob Jones', gaming_username='BobBB',
            status=Registration.Status.REJECTED,
        )

    def test_search_by_name(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/', {'search': 'Alice'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['id'], self.reg1.pk)

    def test_filter_by_status(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/', {'status': 'rejected'})
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['id'], self.reg2.pk)

    def test_cross_organizer_cannot_list(self):
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_export_csv(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/export/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        body = resp.content.decode()
        self.assertIn('Alice Smith', body)
        self.assertIn('Bob Jones', body)

    def test_export_cross_organizer_forbidden(self):
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/registrations/export/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class RegistrationHistoryTests(LifecycleTestBase):
    def test_review_action_appears_in_history(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(
            tournament=tournament, player=self.player, status=Registration.Status.PENDING,
        )
        self.client.force_authenticate(user=self.organizer_user)
        self.client.patch(f'/api/registrations/{registration.pk}/review/', {'status': 'approved'}, format='json')
        resp = self.client.get(f'/api/registrations/{registration.pk}/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(e['action'] == 'registration.approved' for e in resp.data))

    def test_history_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/registrations/{registration.pk}/history/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TeamRosterTests(LifecycleTestBase):
    def setUp(self):
        super().setUp()
        self.tournament = self._draft(status=Tournament.Status.APPROVED, team_size=2)
        self.captain = self.player
        self.member2 = User.objects.create_user(email='lc-member2@example.com', password='StrongPass123')
        self.substitute_player = User.objects.create_user(email='lc-sub@example.com', password='StrongPass123')
        self.team = Team.objects.create(tournament=self.tournament, name='Alpha', captain=self.captain)
        TeamMembership.objects.create(team=self.team, player=self.captain)
        TeamMembership.objects.create(team=self.team, player=self.member2)

    def test_organizer_can_list_all_teams(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/teams/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['id'], self.team.pk)

    def test_organizer_team_list_cross_organizer_forbidden(self):
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/teams/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_lock_by_organizer(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/teams/{self.team.pk}/lock/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['is_locked'])

    def test_lock_cross_organizer_forbidden(self):
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/teams/{self.team.pk}/lock/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_double_lock_rejected(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/teams/{self.team.pk}/lock/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_blocked_when_locked(self):
        self.team.is_locked = True
        self.team.save()
        joiner = User.objects.create_user(email='lc-joiner@example.com', password='StrongPass123')
        self.client.force_authenticate(user=joiner)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/teams/join/', {'invite_code': self.team.invite_code})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_leave_blocked_when_locked(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.member2)
        resp = self.client.post(f'/api/teams/{self.team.pk}/leave/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unlock_requires_staff_not_organizer(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/teams/{self.team.pk}/unlock/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unlock_by_staff_succeeds(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/teams/{self.team.pk}/unlock/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertFalse(resp.data['is_locked'])

    def test_substitute_requires_staff_not_organizer(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/teams/{self.team.pk}/substitute/', {
            'outgoing_player_id': self.member2.pk, 'incoming_player_id': self.substitute_player.pk, 'reason': 'injury',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_substitute_requires_locked_roster(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/teams/{self.team.pk}/substitute/', {
            'outgoing_player_id': self.member2.pk, 'incoming_player_id': self.substitute_player.pk, 'reason': 'injury',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_substitute_success(self):
        self.team.is_locked = True
        self.team.save()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f'/api/teams/{self.team.pk}/substitute/', {
            'outgoing_player_id': self.member2.pk, 'incoming_player_id': self.substitute_player.pk, 'reason': 'injury',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        member_ids = set(TeamMembership.objects.filter(team=self.team).values_list('player_id', flat=True))
        self.assertIn(self.substitute_player.pk, member_ids)
        self.assertNotIn(self.member2.pk, member_ids)

    def test_team_history_shows_lock_action(self):
        self.client.force_authenticate(user=self.organizer_user)
        self.client.post(f'/api/teams/{self.team.pk}/lock/')
        resp = self.client.get(f'/api/teams/{self.team.pk}/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(e['action'] == 'team.roster_locked' for e in resp.data))

    def test_team_history_cross_organizer_forbidden(self):
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.get(f'/api/teams/{self.team.pk}/history/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class RegistrationDisqualifyTests(LifecycleTestBase):
    def test_disqualify_by_organizer(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(tournament=tournament, player=self.player, checked_in=True)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/disqualify/', {'reason': 'Cheating'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], Registration.Status.DISQUALIFIED)
        registration.refresh_from_db()
        self.assertFalse(registration.checked_in)
        self.assertEqual(registration.disqualified_by_id, self.organizer_user.pk)

    def test_disqualify_requires_reason(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/disqualify/', {'reason': ''})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disqualify_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/disqualify/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_disqualified_cannot_be_disqualified_again(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        registration = Registration.objects.create(
            tournament=tournament, player=self.player, status=Registration.Status.DISQUALIFIED,
        )
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/registrations/{registration.pk}/disqualify/', {'reason': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TournamentRulesTests(LifecycleTestBase):
    def test_no_rules_published_returns_null(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, is_published=True)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data)

    def test_get_rules_is_public_once_published(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, is_published=True)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='Be nice.')
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['version'], 1)
        self.assertEqual(resp.data['conduct_rules'], 'Be nice.')

    def test_unpublished_tournament_rules_not_publicly_visible(self):
        # Regression test for an IDOR/PII-leak fix: GET used to be AllowAny
        # with no visibility check at all, so an unpublished (or draft/
        # pending) tournament's rules — and the real email of whoever
        # published them — were readable by anyone who guessed the ID.
        tournament = self._draft(status=Tournament.Status.APPROVED, created_by=self.organizer_user)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='Not public yet.')

        # Anonymous: DRF reports "not authenticated" (401) rather than
        # "forbidden" (403) for a denied request with no successful
        # authenticator, same as every other anonymous-denied case in this
        # file (e.g. test_post_requires_auth above).
        anon_resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(anon_resp.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.player)
        outsider_resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(outsider_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_request_not_treated_as_owner_of_a_tournament_with_no_creator(self):
        # Regression test: Tournament.created_by is SET_NULL (survives the
        # creator's account being deleted), and an anonymous request's own
        # `request.user.pk` is also None — IsPublicOrOwner must not let
        # `None == None` slip an unpublished tournament's rules through to
        # literally anyone just because its creator's account was deleted.
        tournament = self._draft(status=Tournament.Status.APPROVED)  # created_by left unset (None)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='Not public yet.')
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owning_organizer_can_see_unpublished_rules(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, created_by=self.organizer_user)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='Draft rules.')
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_rules_response_never_includes_an_email(self):
        tournament = self._draft(status=Tournament.Status.APPROVED, is_published=True)
        TournamentRuleVersion.objects.create(
            tournament=tournament, version=1, conduct_rules='Be nice.', created_by=self.organizer_user,
        )
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('created_by_email', resp.data)
        self.assertEqual(resp.data['created_by_name'], f'User #{self.organizer_user.pk}')

    def test_organizer_can_publish_first_version(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/rules/', {
            'match_format_rules': 'Best of 3.', 'conduct_rules': 'No smurfing.',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['version'], 1)

    def test_publishing_again_increments_version_and_keeps_history(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.organizer_user)
        self.client.post(f'/api/tournaments/{tournament.pk}/rules/', {'conduct_rules': 'v1 rules'})
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/rules/', {'conduct_rules': 'v2 rules'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['version'], 2)
        self.assertEqual(TournamentRuleVersion.objects.filter(tournament=tournament).count(), 2)
        # the old version's content is untouched, not overwritten
        v1 = TournamentRuleVersion.objects.get(tournament=tournament, version=1)
        self.assertEqual(v1.conduct_rules, 'v1 rules')

    def test_publish_requires_at_least_one_section(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/rules/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_cross_organizer_forbidden(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        self.client.force_authenticate(user=self.other_organizer_user)
        resp = self.client.post(f'/api/tournaments/{tournament.pk}/rules/', {'conduct_rules': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_history_lists_every_version_staff_or_organizer_only(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='a')
        TournamentRuleVersion.objects.create(tournament=tournament, version=2, conduct_rules='b')

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

        self.client.force_authenticate(user=self.player)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/rules/history/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class RegistrationRulesAcknowledgementTests(LifecycleTestBase):
    def _register(self, tournament):
        self.client.force_authenticate(user=self.player)
        return self.client.post('/api/registrations/', {
            'tournament': tournament.pk, 'full_name': 'P', 'gaming_username': 'p', 'phone_number': '+923001234567',
            'contact_email': 'lc-player@example.com', 'country': 'PK', 'city': 'Lahore',
            'platform': 'Steam', 'platform_username': 'p', 'accepted_rules': True, 'accepted_code_of_conduct': True,
        })

    def test_registering_before_any_rules_published_leaves_version_null(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        resp = self._register(tournament)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data['accepted_rules_version'])
        self.assertFalse(resp.data['rules_outdated'])

    def test_registering_after_rules_published_stamps_current_version(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='x')
        resp = self._register(tournament)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['accepted_rules_version'], 1)
        self.assertFalse(resp.data['rules_outdated'])

    def test_rules_outdated_flag_true_after_new_version_published(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='x')
        self._register(tournament)
        TournamentRuleVersion.objects.create(tournament=tournament, version=2, conduct_rules='y')

        registration = Registration.objects.get(tournament=tournament, player=self.player)
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{tournament.pk}/registrations/')
        row = next(r for r in resp.data if r['id'] == registration.pk)
        self.assertTrue(row['rules_outdated'])

    def test_acknowledge_rules_updates_version(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='x')
        self._register(tournament)
        TournamentRuleVersion.objects.create(tournament=tournament, version=2, conduct_rules='y')
        registration = Registration.objects.get(tournament=tournament, player=self.player)

        self.client.force_authenticate(user=self.player)
        resp = self.client.post(f'/api/registrations/{registration.pk}/acknowledge-rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['accepted_rules_version'], 2)
        self.assertFalse(resp.data['rules_outdated'])

    def test_acknowledge_rules_forbidden_for_other_player(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        TournamentRuleVersion.objects.create(tournament=tournament, version=1, conduct_rules='x')
        self._register(tournament)
        registration = Registration.objects.get(tournament=tournament, player=self.player)

        outsider = User.objects.create_user(email='lc-outsider@example.com', password='StrongPass123')
        self.client.force_authenticate(user=outsider)
        resp = self.client.post(f'/api/registrations/{registration.pk}/acknowledge-rules/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_acknowledge_with_no_published_rules_rejected(self):
        tournament = self._draft(status=Tournament.Status.APPROVED)
        resp = self._register(tournament)
        registration_id = resp.data['id']
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(f'/api/registrations/{registration_id}/acknowledge-rules/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
