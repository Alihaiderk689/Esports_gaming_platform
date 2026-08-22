import re
from io import BytesIO
from unittest.mock import patch

import cloudinary.exceptions
import fitz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog, Dispute, Follow, PendingRegistration
from organizer.models import Organizer

User = get_user_model()


def _extract_otp(message):
    match = re.search(r'\b(\d{6})\b', message.body)
    assert match, f'no 6-digit code found in email body: {message.body!r}'
    return match.group(1)


def _make_jpeg_bytes():
    buf = BytesIO()
    Image.new('RGB', (10, 10), color='blue').save(buf, format='JPEG')
    return buf.getvalue()


def _make_pdf_bytes():
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


# Genuinely decodable, not just correct magic bytes — validate_document_file
# (core/validators.py) actually opens these with Pillow/PyMuPDF, not just
# sniffs the header.
_JPEG_BYTES = _make_jpeg_bytes()
_PDF_BYTES = _make_pdf_bytes()


class HealthCheckApiTests(APITestCase):
    def test_health_check_ok(self):
        resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {'status': 'ok'})

    def test_core_health_check_ok(self):
        # /api/core/health/ — same view, second path, pinged by the GitHub
        # Actions keep-alive workflow (.github/workflows/health-check.yml).
        resp = self.client.get('/api/core/health/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {'status': 'ok'})

    def test_health_check_requires_no_auth(self):
        resp = self.client.get('/api/core/health/')
        self.assertNotEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PlayerApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='alice@example.com', password='StrongPass123', first_name='Alice')
        self.other = User.objects.create_user(email='bob@example.com', password='StrongPass123', first_name='Bob')
        self.third = User.objects.create_user(email='carl@example.com', password='StrongPass123', first_name='Carl')
        self.admin = User.objects.create_user(
            email='admin@example.com', password='StrongPass123', first_name='Admin', is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_list_players_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/players/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_players(self):
        resp = self.client.get('/api/players/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        emails = {p['email'] for p in self._results(resp)}
        self.assertIn('alice@example.com', emails)
        self.assertIn('bob@example.com', emails)

    def test_list_players_search(self):
        resp = self.client.get('/api/players/', {'search': 'bob'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['email'], 'bob@example.com')

    def test_list_players_no_search_returns_all(self):
        resp = self.client.get('/api/players/')
        self.assertGreaterEqual(len(self._results(resp)), 4)

    def test_retrieve_player(self):
        resp = self.client.get(f'/api/players/{self.other.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['email'], 'bob@example.com')
        self.assertIn('followers_count', resp.data)
        self.assertIn('is_following', resp.data)

    def test_get_me(self):
        resp = self.client.get('/api/players/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['email'], 'alice@example.com')

    def test_patch_me(self):
        resp = self.client.patch('/api/players/me/', {'first_name': 'Alicia'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Alicia')

    def test_patch_other_via_id_forbidden_for_non_admin(self):
        resp = self.client.patch(f'/api/players/{self.other.pk}/', {'first_name': 'Hacked'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, 'Bob')

    def test_patch_via_id_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/players/{self.other.pk}/', {'first_name': 'Renamed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, 'Renamed')

    def test_delete_other_via_id_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/players/{self.other.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())

    def test_delete_via_id_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/players/{self.other.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.other.pk).exists())

    def test_delete_me(self):
        resp = self.client.delete('/api/players/me/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_organizer_with_tournament_cannot_self_delete(self):
        # Regression test for a real data-integrity bug: Organizer.user used
        # to be CASCADE, so this endpoint let an approved organizer delete
        # their own account and silently take every tournament they'd ever
        # run — and everything downstream of those (registrations, brackets,
        # matches, disputes) for every *other* player who participated —
        # down with it. Should be a clean 400, not a 500, and definitely not
        # a successful 204.
        from games.models import Game
        from organizer.models import Organizer
        from tourny_regist.models import Tournament

        organizer_user = User.objects.create_user(email='org-selfdelete@example.com', password='StrongPass123!')
        organizer = Organizer.objects.create(
            user=organizer_user, company_name='Acme', status=Organizer.Status.APPROVED,
        )
        game = Game.objects.create(name='Valorant', genre='FPS')
        tournament = Tournament.objects.create(name='Cup', game=game, organizer=organizer)

        self.client.force_authenticate(user=organizer_user)
        resp = self.client.delete('/api/players/me/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(pk=organizer_user.pk).exists())
        self.assertTrue(Organizer.objects.filter(pk=organizer.pk).exists())
        self.assertTrue(Tournament.objects.filter(pk=tournament.pk).exists())

    def test_admin_cannot_delete_organizer_with_tournament_via_id(self):
        from games.models import Game
        from organizer.models import Organizer
        from tourny_regist.models import Tournament

        organizer_user = User.objects.create_user(email='org-admindelete@example.com', password='StrongPass123!')
        organizer = Organizer.objects.create(
            user=organizer_user, company_name='Acme', status=Organizer.Status.APPROVED,
        )
        game = Game.objects.create(name='Valorant', genre='FPS')
        Tournament.objects.create(name='Cup', game=game, organizer=organizer)

        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/players/{organizer_user.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.filter(pk=organizer_user.pk).exists())

    def test_follow_and_top_and_following(self):
        resp = self.client.post(f'/api/players/{self.other.pk}/follow/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Follow.objects.filter(follower=self.user, following=self.other).exists())

        # third also follows bob, so bob should be top
        self.client.force_authenticate(user=self.third)
        self.client.post(f'/api/players/{self.other.pk}/follow/')
        self.client.force_authenticate(user=self.user)

        top_resp = self.client.get('/api/players/top/')
        top_results = self._results(top_resp)
        self.assertEqual(top_results[0]['email'], 'bob@example.com')
        self.assertEqual(top_results[0]['followers_count'], 2)

        following_resp = self.client.get('/api/players/following/')
        following_results = self._results(following_resp)
        self.assertEqual(len(following_results), 1)
        self.assertEqual(following_results[0]['email'], 'bob@example.com')

    def test_follow_self_rejected(self):
        resp = self.client.post(f'/api/players/{self.user.pk}/follow/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_follow_duplicate_rejected(self):
        self.client.post(f'/api/players/{self.other.pk}/follow/')
        resp = self.client.post(f'/api/players/{self.other.pk}/follow/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_follow_nonexistent_player(self):
        resp = self.client.post('/api/players/999999/follow/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unfollow(self):
        self.client.post(f'/api/players/{self.other.pk}/follow/')
        resp = self.client.delete(f'/api/players/{self.other.pk}/follow/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Follow.objects.filter(follower=self.user, following=self.other).exists())

    def test_unfollow_not_following(self):
        resp = self.client.delete(f'/api/players/{self.other.pk}/follow/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RegisterApiTests(APITestCase):
    def _payload(self, **overrides):
        payload = {
            'email': 'newplayer@example.com',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'first_name': 'John',
            'last_name': "O'Connor",
        }
        payload.update(overrides)
        return payload

    def test_register_success(self):
        resp = self.client.post('/api/auth/register/', self._payload())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        # No account exists until the emailed link is clicked - only a pending row.
        self.assertFalse(User.objects.filter(email='newplayer@example.com').exists())
        self.assertTrue(PendingRegistration.objects.filter(email='newplayer@example.com').exists())

    def test_register_normalizes_email_case_and_whitespace(self):
        resp = self.client.post('/api/auth/register/', self._payload(email='  John@Example.com  '))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertFalse(User.objects.filter(email='john@example.com').exists())
        self.assertTrue(PendingRegistration.objects.filter(email='john@example.com').exists())

    def test_register_duplicate_email_rejected(self):
        User.objects.create_user(email='taken@example.com', password='StrongPass123!')
        resp = self.client.post('/api/auth/register/', self._payload(email='taken@example.com'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already registered', str(resp.data['email']))

    def test_register_duplicate_email_case_insensitive(self):
        User.objects.create_user(email='taken@example.com', password='StrongPass123!')
        resp = self.client.post('/api/auth/register/', self._payload(email='Taken@Example.com'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_password_mismatch_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(confirm_password='Different123!'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', resp.data)

    def test_register_weak_password_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(password='password', confirm_password='password'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', resp.data)

    def test_register_password_too_long_rejected(self):
        long_password = 'Aa1!' * 40  # 160 chars, well past the 128 cap
        resp = self.client.post(
            '/api/auth/register/', self._payload(password=long_password, confirm_password=long_password),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', resp.data)

    def test_register_missing_first_name_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(first_name=''))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', resp.data)

    def test_register_first_name_too_short_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(first_name='A'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', resp.data)

    def test_register_first_name_with_digits_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(first_name='John123'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', resp.data)

    def test_register_first_name_with_symbols_rejected(self):
        resp = self.client.post('/api/auth/register/', self._payload(first_name='@john'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', resp.data)

    def test_register_last_name_hyphenated_accepted(self):
        resp = self.client.post('/api/auth/register/', self._payload(last_name='Smith-Jones'))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_register_name_with_multiple_words_accepted(self):
        resp = self.client.post('/api/auth/register/', self._payload(first_name='Mary Jane'))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_register_again_before_verifying_refreshes_pending_row(self):
        self.client.post('/api/auth/register/', self._payload(first_name='John'))
        resp = self.client.post('/api/auth/register/', self._payload(first_name='Jonathan'))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(PendingRegistration.objects.filter(email='newplayer@example.com').count(), 1)
        self.assertEqual(
            PendingRegistration.objects.get(email='newplayer@example.com').first_name, 'Jonathan',
        )


class VerifyEmailApiTests(APITestCase):
    def setUp(self):
        # verify-email/resend share the 'email_action' throttle scope (5/hour), which
        # is cache-backed and doesn't reset between test methods on its own.
        cache.clear()

    def _register(self, **overrides):
        payload = {
            'email': 'pending@example.com',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'first_name': 'Jane',
            'last_name': 'Doe',
        }
        payload.update(overrides)
        resp = self.client.post('/api/auth/register/', payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        pending = PendingRegistration.objects.get(email=payload['email'].strip().lower())
        otp = _extract_otp(mail.outbox[-1])
        return pending, otp

    def test_verify_creates_user_and_deletes_pending(self):
        pending, otp = self._register()
        resp = self.client.post('/api/auth/verify-email/', {'email': pending.email, 'otp': otp})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        user = User.objects.get(email='pending@example.com')
        self.assertTrue(user.is_email_verified)
        self.assertFalse(PendingRegistration.objects.filter(pk=pending.pk).exists())

        # Proves password_hash round-trips correctly (no double-hashing).
        login_resp = self.client.post(
            '/api/auth/login/', {'email': 'pending@example.com', 'password': 'StrongPass123!'},
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK, login_resp.data)

    def test_verify_wrong_otp_rejected(self):
        pending, otp = self._register()
        wrong = '000000' if otp != '000000' else '111111'
        resp = self.client.post('/api/auth/verify-email/', {'email': pending.email, 'otp': wrong})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['attempts_remaining'], '4')
        self.assertFalse(User.objects.filter(email='pending@example.com').exists())
        self.assertTrue(PendingRegistration.objects.filter(pk=pending.pk).exists())

    def test_verify_unknown_email_rejected(self):
        resp = self.client.post('/api/auth/verify-email/', {'email': 'nobody@example.com', 'otp': '123456'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_expired_otp_rejected(self):
        pending, otp = self._register()
        PendingRegistration.objects.filter(pk=pending.pk).update(
            otp_expires_at=timezone.now() - timezone.timedelta(seconds=1),
        )
        resp = self.client.post('/api/auth/verify-email/', {'email': pending.email, 'otp': otp})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('expired', resp.data['otp'])
        self.assertTrue(PendingRegistration.objects.filter(pk=pending.pk).exists())

    def test_verify_locks_out_after_max_attempts(self):
        pending, otp = self._register()
        wrong = '000000' if otp != '000000' else '111111'
        for _ in range(4):
            resp = self.client.post('/api/auth/verify-email/', {'email': pending.email, 'otp': wrong})
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 5th wrong attempt trips the lockout — the correct code no longer works either.
        resp = self.client.post('/api/auth/verify-email/', {'email': pending.email, 'otp': wrong})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Too many incorrect attempts', resp.data['otp'])
        self.assertNotIn('attempts_remaining', resp.data)


class VerifyEmailOrganizerApiTests(APITestCase):
    def setUp(self):
        cache.clear()  # see VerifyEmailApiTests.setUp — same throttle-reset reason
        # cnic_document/company_document live in Cloudinary (CloudinarySignedStorage),
        # so no local files are ever written — just patch the SDK calls instead of
        # hitting the network, same pattern as organizer/tests.py's OrganizerApiTests.
        self.mock_upload = patch('cloudinary.uploader.upload').start()
        self.mock_upload.return_value = {'public_id': 'test/fake-public-id'}
        self.mock_resource = patch(
            'cloudinary.api.resource', side_effect=cloudinary.exceptions.NotFound('not found'),
        ).start()
        self.addCleanup(patch.stopall)

    def test_verify_organizer_creates_organizer_profile(self):
        cnic_file = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES, content_type='image/jpeg')
        company_file = SimpleUploadedFile('registration.pdf', _PDF_BYTES, content_type='application/pdf')
        resp = self.client.post('/api/auth/register/', {
            'email': 'org@example.com',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'first_name': 'Org',
            'last_name': 'Owner',
            'role': 'organizer',
            'company_name': 'Acme Esports',
            'cnic_document': cnic_file,
            'company_document': company_file,
            'payout_method': 'jazzcash',
            'jazzcash_number': '03001234567',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        pending = PendingRegistration.objects.get(email='org@example.com')
        otp = _extract_otp(mail.outbox[-1])
        verify_resp = self.client.post('/api/auth/verify-email/', {'email': 'org@example.com', 'otp': otp})
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK, verify_resp.data)

        user = User.objects.get(email='org@example.com')
        organizer = Organizer.objects.get(user=user)
        self.assertEqual(organizer.company_name, 'Acme Esports')
        self.assertTrue(organizer.cnic_document)
        self.assertTrue(organizer.company_document)
        self.assertFalse(PendingRegistration.objects.filter(pk=pending.pk).exists())


class ResendVerificationApiTests(APITestCase):
    def setUp(self):
        cache.clear()  # see VerifyEmailApiTests.setUp — same throttle-reset reason

    def test_resend_sends_new_code_for_pending(self):
        self.client.post('/api/auth/register/', {
            'email': 'resend@example.com', 'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'first_name': 'Res', 'last_name': 'End',
        })
        # Clear the resend cooldown set by registration's own send, so this
        # exercises the "resend after the cooldown has passed" path.
        PendingRegistration.objects.filter(email='resend@example.com').update(otp_last_sent_at=None)
        mail.outbox.clear()
        resp = self.client.post('/api/auth/resend-verification/', {'email': 'resend@example.com'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('resend@example.com', mail.outbox[0].to)

    def test_resend_silent_for_unknown_email(self):
        resp = self.client.post('/api/auth/resend-verification/', {'email': 'nobody@example.com'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_respects_cooldown(self):
        self.client.post('/api/auth/register/', {
            'email': 'cooldown@example.com', 'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'first_name': 'Cool', 'last_name': 'Down',
        })
        mail.outbox.clear()
        # Immediately re-requesting a code, inside the 60s cooldown, is a silent no-op.
        resp = self.client.post('/api/auth/resend-verification/', {'email': 'cooldown@example.com'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_verify_still_works_after_a_resend(self):
        self.client.post('/api/auth/register/', {
            'email': 'tworesend@example.com', 'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'first_name': 'Two', 'last_name': 'Resend',
        })
        pending = PendingRegistration.objects.get(email='tworesend@example.com')
        pending.otp_last_sent_at = None
        pending.save(update_fields=['otp_last_sent_at'])
        mail.outbox.clear()
        resp = self.client.post('/api/auth/resend-verification/', {'email': 'tworesend@example.com'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

        otp = _extract_otp(mail.outbox[-1])
        verify_resp = self.client.post('/api/auth/verify-email/', {'email': 'tworesend@example.com', 'otp': otp})
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK, verify_resp.data)


class LoginApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='caseuser@example.com', password='StrongPass123!')

    def test_login_email_case_insensitive(self):
        resp = self.client.post('/api/auth/login/', {'email': 'CaseUser@Example.com', 'password': 'StrongPass123!'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['user']['email'], 'caseuser@example.com')

    def test_login_throttled_per_account_even_across_different_ips(self):
        # The IP-scoped 'login' throttle alone wouldn't catch this: every
        # attempt below comes from a distinct address, so it never
        # accumulates past 1 there. LoginEmailRateThrottle (core/throttling.py)
        # is what actually stops a credential-stuffing run distributed across
        # many IPs against one account.
        for i in range(10):
            resp = self.client.post(
                '/api/auth/login/',
                {'email': self.user.email, 'password': 'WrongPass!123'},
                REMOTE_ADDR=f'10.0.0.{i}',
            )
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        resp = self.client.post(
            '/api/auth/login/',
            {'email': self.user.email, 'password': 'WrongPass!123'},
            REMOTE_ADDR='10.0.0.99',
        )
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class GoogleLoginApiTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _payload(self, nonce, **overrides):
        payload = {
            'email': 'googleuser@example.com', 'email_verified': True,
            'sub': 'google-sub-123', 'given_name': 'Goo', 'family_name': 'Gler',
            'nonce': nonce,
        }
        payload.update(overrides)
        return payload

    def _start(self):
        resp = self.client.get('/api/auth/google/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data['nonce'], resp.data['state']

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_unverified_email_rejected(self, mock_verify):
        nonce, state = self._start()
        mock_verify.return_value = self._payload(nonce, email_verified=False)
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='googleuser@example.com').exists())

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_verified_email_accepted(self, mock_verify):
        nonce, state = self._start()
        mock_verify.return_value = self._payload(nonce)
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(User.objects.filter(email='googleuser@example.com').exists())

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_network_failure_returns_503_not_400(self, mock_verify):
        from google.auth.exceptions import TransportError

        nonce, state = self._start()
        mock_verify.side_effect = TransportError('could not reach Google')
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, resp.data)

    def test_google_login_requires_state(self):
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_login_rejects_garbage_state(self):
        resp = self.client.post(
            '/api/auth/google-login/', {'id_token': 'fake-token', 'state': 'not-a-real-signed-value'},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('state', resp.data)

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_rejects_id_token_whose_nonce_claim_doesnt_match_state(self, mock_verify):
        # A token minted for a *different* login attempt (different nonce) —
        # this is exactly what GoogleOAuthStartView/GoogleLoginView's
        # server-side re-derivation is meant to catch, as opposed to the
        # previous client-side-only nonce check.
        _, state = self._start()
        mock_verify.return_value = self._payload('some-other-attempts-nonce')
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='googleuser@example.com').exists())

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_state_cannot_be_replayed_after_a_successful_login(self, mock_verify):
        nonce, state = self._start()
        mock_verify.return_value = self._payload(nonce)

        first = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)

        second = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token', 'state': state})
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)


class SessionRevocationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='revoke@example.com', password='StrongPass123!')
        # RefreshToken.for_user only creates an OutstandingToken row via the
        # blacklist app's save hook when the token is actually persisted — force
        # that by touching str() on it, same as the login view path does.
        self.refresh = RefreshToken.for_user(self.user)
        str(self.refresh)
        self.client.force_authenticate(user=self.user)

    def _outstanding(self):
        return OutstandingToken.objects.filter(user=self.user)

    def test_change_password_revokes_outstanding_tokens(self):
        self.assertFalse(BlacklistedToken.objects.filter(token__in=self._outstanding()).exists())
        resp = self.client.post('/api/auth/change-password/', {
            'current_password': 'StrongPass123!',
            'new_password': 'EvenStrongerPass456!', 'confirm_password': 'EvenStrongerPass456!',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        outstanding = self._outstanding()
        self.assertTrue(outstanding.exists())
        for token in outstanding:
            self.assertTrue(BlacklistedToken.objects.filter(token=token).exists())

    def test_reset_password_revokes_outstanding_tokens(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        from core.tokens import password_reset_token

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = password_reset_token.make_token(self.user)
        resp = self.client.post('/api/auth/reset-password/', {
            'uid': uid, 'token': token,
            'new_password': 'EvenStrongerPass456!', 'confirm_password': 'EvenStrongerPass456!',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        outstanding = self._outstanding()
        self.assertTrue(outstanding.exists())
        for t in outstanding:
            self.assertTrue(BlacklistedToken.objects.filter(token=t).exists())

    def test_logout_all_revokes_outstanding_tokens(self):
        self.assertFalse(BlacklistedToken.objects.filter(token__in=self._outstanding()).exists())
        resp = self.client.post('/api/auth/logout-all/')
        self.assertEqual(resp.status_code, status.HTTP_205_RESET_CONTENT)
        outstanding = self._outstanding()
        self.assertTrue(outstanding.exists())
        for token in outstanding:
            self.assertTrue(BlacklistedToken.objects.filter(token=token).exists())

    def test_logout_all_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/auth/logout-all/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class DisputeTestMixin:
    """Shared fixtures: an approved tournament with two checked-in players, plus
    staff and an outsider account to exercise every permission tier a dispute
    endpoint has to enforce."""

    def setUp(self):
        from games.models import Game
        from tourny_regist.models import Registration, Tournament

        self.game = Game.objects.create(name='DisputeTestGame', genre='FPS')
        self.organizer_user = User.objects.create_user(email='dispute-organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(
            user=self.organizer_user, company_name='Dispute Co', status=Organizer.Status.APPROVED,
        )
        self.player1 = User.objects.create_user(email='dispute-player1@example.com', password='StrongPass123')
        self.player2 = User.objects.create_user(email='dispute-player2@example.com', password='StrongPass123')
        self.outsider = User.objects.create_user(email='dispute-outsider@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(email='dispute-admin@example.com', password='StrongPass123', is_staff=True)
        self.tournament = Tournament.objects.create(
            name='Dispute Tournament', game=self.game, organizer=self.organizer,
            status=Tournament.Status.APPROVED, created_by=self.organizer_user,
        )
        Registration.objects.create(tournament=self.tournament, player=self.player1, checked_in=True)
        Registration.objects.create(tournament=self.tournament, player=self.player2, checked_in=True)

    def _dispute(self):
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/disputes/', {'description': 'issue'})
        return Dispute.objects.get(pk=resp.data['id'])


class TournamentDisputeTests(DisputeTestMixin, APITestCase):
    def test_registered_player_can_file_a_dispute(self):
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(
            f'/api/tournaments/{self.tournament.pk}/disputes/', {'description': 'Wrong bracket seeding'},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        dispute = Dispute.objects.get()
        self.assertEqual(dispute.filed_by_id, self.player1.pk)
        self.assertEqual(dispute.status, Dispute.Status.OPEN)

    def test_outsider_cannot_file_a_dispute(self):
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/disputes/', {'description': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_description_rejected(self):
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/tournaments/{self.tournament.pk}/disputes/', {'description': '   '})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_can_list_disputes_outsider_cannot(self):
        self._dispute()

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/disputes/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

        self.client.force_authenticate(user=self.outsider)
        resp = self.client.get(f'/api/tournaments/{self.tournament.pk}/disputes/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MatchDisputeTests(DisputeTestMixin, APITestCase):
    def _match(self):
        from brackets.models import Match
        from brackets.services import generate_bracket
        bracket = generate_bracket(self.tournament)
        return Match.objects.get(bracket=bracket)

    def test_match_participant_can_file_a_dispute(self):
        match = self._match()
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/matches/{match.pk}/disputes/', {'description': 'lag caused a false loss'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        dispute = Dispute.objects.get()
        self.assertEqual(dispute.object_id, match.pk)

    def test_non_participant_cannot_file_a_match_dispute(self):
        match = self._match()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(f'/api/matches/{match.pk}/disputes/', {'description': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_match_dispute_detail_shows_tournament_context(self):
        match = self._match()
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/matches/{match.pk}/disputes/', {'description': 'x'})
        dispute_id = resp.data['id']

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get(f'/api/disputes/{dispute_id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(self.tournament.name, resp.data['target_label'])
        self.assertEqual(resp.data['target_tournament_id'], self.tournament.pk)


class DisputeEvidenceTests(DisputeTestMixin, APITestCase):
    def test_stakeholder_can_upload_evidence(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        evidence_file = SimpleUploadedFile('proof.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post(f'/api/disputes/{dispute.pk}/evidence/', {'file': evidence_file}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(dispute.evidence.count(), 1)

    def test_evidence_rejects_non_image_content(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        malicious = SimpleUploadedFile('proof.jpg', b'<script>alert(1)</script>', content_type='image/jpeg')
        resp = self.client.post(f'/api/disputes/{dispute.pk}/evidence/', {'file': malicious}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_stakeholder_cannot_upload_evidence(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.outsider)
        evidence_file = SimpleUploadedFile('proof.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post(f'/api/disputes/{dispute.pk}/evidence/', {'file': evidence_file}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_upload_evidence_to_a_resolved_dispute(self):
        # Business-logic regression test: evidence upload previously had no
        # status check at all (unlike DisputeStatusView, which correctly
        # blocks further status changes once resolved/dismissed) — a
        # stakeholder could keep attaching "evidence" to a dispute's record
        # indefinitely after its decision was already made.
        dispute = self._dispute()
        self.client.force_authenticate(user=self.organizer_user)
        self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'decided',
        }, format='json')

        self.client.force_authenticate(user=self.player1)
        evidence_file = SimpleUploadedFile('proof.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post(f'/api/disputes/{dispute.pk}/evidence/', {'file': evidence_file}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(dispute.evidence.count(), 0)


class DisputeStatusTests(DisputeTestMixin, APITestCase):
    def test_organizer_can_resolve(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'Verified seeding was correct.',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, Dispute.Status.RESOLVED)
        self.assertEqual(dispute.resolved_by_id, self.organizer_user.pk)
        self.assertIsNotNone(dispute.resolved_at)

    def test_resolution_notes_required_to_resolve(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {'status': 'resolved'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_player_cannot_resolve_their_own_dispute(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'dismissed', 'resolution_notes': 'nvm',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_resolve_an_already_resolved_dispute(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.organizer_user)
        self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'done',
        }, format='json')
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'dismissed', 'resolution_notes': 'again',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class DisputeEscalationTests(DisputeTestMixin, APITestCase):
    def test_filer_can_escalate(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/disputes/{dispute.pk}/escalate/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        dispute.refresh_from_db()
        self.assertTrue(dispute.escalated_to_admin)

    def test_organizer_cannot_resolve_once_escalated(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        self.client.post(f'/api/disputes/{dispute.pk}/escalate/')

        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_resolve_an_escalated_dispute(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        self.client.post(f'/api/disputes/{dispute.pk}/escalate/')

        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'reviewed by admin',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_outsider_cannot_escalate(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.outsider)
        resp = self.client.post(f'/api/disputes/{dispute.pk}/escalate/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_double_escalation_rejected(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        self.client.post(f'/api/disputes/{dispute.pk}/escalate/')
        resp = self.client.post(f'/api/disputes/{dispute.pk}/escalate/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_escalate_a_resolved_dispute(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.organizer_user)
        self.client.patch(f'/api/disputes/{dispute.pk}/status/', {
            'status': 'resolved', 'resolution_notes': 'decided',
        }, format='json')

        self.client.force_authenticate(user=self.player1)
        resp = self.client.post(f'/api/disputes/{dispute.pk}/escalate/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        dispute.refresh_from_db()
        self.assertFalse(dispute.escalated_to_admin)


class DisputeMineAndAdminListTests(DisputeTestMixin, APITestCase):
    def test_mine_lists_only_own_disputes(self):
        self._dispute()
        self.client.force_authenticate(user=self.player2)
        self.client.post(f'/api/tournaments/{self.tournament.pk}/disputes/', {'description': 'b'})

        self.client.force_authenticate(user=self.player1)
        resp = self.client.get('/api/disputes/mine/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['description'], 'issue')

    def test_admin_list_sees_every_dispute(self):
        self._dispute()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get('/api/admin/disputes/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_admin_list_filters_by_escalated(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        self.client.post(f'/api/disputes/{dispute.pk}/escalate/')

        self.client.force_authenticate(user=self.admin)
        resp = self.client.get('/api/admin/disputes/', {'escalated': 'true'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_non_staff_cannot_use_admin_list(self):
        self.client.force_authenticate(user=self.organizer_user)
        resp = self.client.get('/api/admin/disputes/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class AuditLogImmutabilityTests(APITestCase):
    """Model-level backstop (core/models.py:AuditLog.save/delete) — there's no
    API path to edit/delete an entry today, but this guarantees that stays
    true even if one gets added by mistake later."""

    def setUp(self):
        self.actor = User.objects.create_user(email='auditor@example.com', password='StrongPass123!')
        # Built through log_action's own path rather than constructing the
        # ContentType by hand — reuse the actor row itself as the target.
        from core.audit import log_action
        log_action(self.actor, 'test.action', self.actor)
        self.entry = AuditLog.objects.get(action='test.action')

    def test_cannot_modify_an_existing_entry(self):
        self.entry.reason = 'tampered'
        with self.assertRaises(ValueError):
            self.entry.save()

    def test_cannot_delete_an_entry(self):
        with self.assertRaises(ValueError):
            self.entry.delete()


class SecurityEventLoggingTests(APITestCase):
    """core.security_events.log_security_event refuses to log a field whose
    name suggests it might carry a secret — a structural backstop for the
    "never log a password/token" rule, not just a comment relying on every
    future call site remembering it."""

    def test_refuses_a_field_named_like_a_secret(self):
        from core.security_events import log_security_event

        for bad_field in ('password', 'current_password', 'refresh_token', 'reset_token', 'id_token', 'Authorization'):
            with self.assertRaises(ValueError):
                log_security_event('test.event', **{bad_field: 'whatever'})

    def test_allows_ordinary_identifying_fields(self):
        from core.security_events import log_security_event

        # Doesn't raise — target_user_id/attempted_email/status_code and
        # similar plain identifiers are exactly what this is for.
        log_security_event('test.event', target_user_id=1, attempted_email='x@example.com', status_code=403)


class AccountDeletionPreservesAccountabilityRecordsTests(DisputeTestMixin, APITestCase):
    """Dispute.filed_by, DisputeEvidence.uploaded_by, and
    AdminReviewRequest.requested_by are all SET_NULL rather than CASCADE
    (core/models.py) — deleting the account that filed/uploaded/requested
    something shouldn't delete the record itself, since other stakeholders
    (the opposing player, the organizer, staff, an already-made admin
    decision) rely on it surviving. Tested at the model/ORM level directly
    (rather than through /api/players/me/) since that endpoint's own guard
    against deleting an organizer with tournaments (ProtectedUserDeleteMixin)
    is a separate concern from what these FKs' on_delete behavior does."""

    def test_dispute_and_its_evidence_survive_the_filer_being_deleted(self):
        dispute = self._dispute()
        self.client.force_authenticate(user=self.player1)
        self.client.post(f'/api/disputes/{dispute.pk}/evidence/', {
            'file': SimpleUploadedFile('proof.jpg', _JPEG_BYTES, content_type='image/jpeg'),
        }, format='multipart')

        self.player1.delete()

        dispute.refresh_from_db()
        self.assertIsNone(dispute.filed_by_id)
        self.assertEqual(dispute.evidence.count(), 1)
        self.assertIsNone(dispute.evidence.first().uploaded_by_id)

    def test_admin_review_request_survives_the_requesting_organizer_being_deleted(self):
        from django.contrib.contenttypes.models import ContentType

        from core.models import AdminReviewRequest

        # organizer_user (DisputeTestMixin) has no tournaments of its own —
        # only self.tournament, owned by self.organizer — so it's directly
        # deletable, isolating this test to the SET_NULL behavior itself.
        requester = User.objects.create_user(email='review-requester@example.com', password='StrongPass123')
        review = AdminReviewRequest.objects.create(
            requested_by=requester,
            request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
            reason='has registrations',
            content_type=ContentType.objects.get_for_model(self.tournament),
            object_id=self.tournament.pk,
        )

        requester.delete()

        review.refresh_from_db()
        self.assertIsNone(review.requested_by_id)


class AdminUserDetailViewTests(APITestCase):
    """Changing another account's is_staff/is_active requires the acting
    admin to re-enter their own current password — a stolen-but-still-valid
    access token shouldn't be enough on its own to mint a second admin
    account or deactivate one. See core.views.AdminUserDetailView.update."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email='reauth-admin@example.com', password='AdminPass123!', is_staff=True,
        )
        self.target = User.objects.create_user(email='reauth-target@example.com', password='StrongPass123')
        self.client.force_authenticate(user=self.admin)

    def test_grant_staff_without_current_password_rejected(self):
        resp = self.client.patch(f'/api/admin/users/{self.target.pk}/', {'is_staff': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)

    def test_grant_staff_with_wrong_current_password_rejected(self):
        resp = self.client.patch(
            f'/api/admin/users/{self.target.pk}/', {'is_staff': True, 'current_password': 'WrongPassword!'},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)

    def test_grant_staff_with_correct_current_password_succeeds_and_is_audited(self):
        resp = self.client.patch(
            f'/api/admin/users/{self.target.pk}/', {'is_staff': True, 'current_password': 'AdminPass123!'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)

        entry = AuditLog.objects.get(action='admin.user_staff_status_changed', object_id=self.target.pk)
        self.assertEqual(entry.actor_id, self.admin.pk)
        self.assertFalse(entry.metadata['before']['is_staff'])
        self.assertTrue(entry.metadata['after']['is_staff'])


class SecuritySettingsInvariantTests(TestCase):
    """Codifies docs/SECURITY_CHECKLIST.md items that are 'already correctly
    implemented' as permanent regression tests — a settings.py edit that
    silently drifts one of these back to something unsafe now fails CI on
    every push instead of only being caught at the next manual checklist
    review."""

    def test_cors_does_not_allow_all_origins(self):
        self.assertFalse(getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False))

    def test_cors_does_not_allow_credentials(self):
        self.assertFalse(settings.CORS_ALLOW_CREDENTIALS)

    def test_jwt_algorithm_is_pinned_to_hs256(self):
        self.assertEqual(settings.SIMPLE_JWT['ALGORITHM'], 'HS256')

    def test_expected_throttle_scopes_are_present(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for scope in (
            'login', 'login_email', 'register', 'email_action', 'email_action_email',
            'chat', 'team_join', 'user', 'anon',
        ):
            self.assertIn(scope, rates, f'{scope!r} missing from DEFAULT_THROTTLE_RATES')

    def test_security_headers_are_set(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')

    def test_exception_handler_is_wired(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['EXCEPTION_HANDLER'], 'core.exceptions.security_aware_exception_handler',
        )


class ProductionMonitoringCheckTests(TestCase):
    """core.checks.production_monitoring_check — advisory warnings that
    surface in Render's deploy logs (entrypoint.sh's `migrate` runs system
    checks by default). See core/apps.py:CoreConfig.ready for registration."""

    def test_no_warnings_outside_production(self):
        from core.checks import production_monitoring_check
        with override_settings(ENVIRONMENT='development', REDIS_URL='', SENTRY_DSN=''):
            self.assertEqual(production_monitoring_check(None), [])

    def test_warns_when_redis_and_sentry_unset_in_production(self):
        from core.checks import production_monitoring_check
        with override_settings(ENVIRONMENT='production', REDIS_URL='', SENTRY_DSN=''):
            warnings = production_monitoring_check(None)
        self.assertEqual({w.id for w in warnings}, {'core.W001', 'core.W002'})

    def test_no_warnings_when_both_set_in_production(self):
        from core.checks import production_monitoring_check
        with override_settings(
            ENVIRONMENT='production', REDIS_URL='redis://localhost:6379/0', SENTRY_DSN='https://x@sentry.io/1',
        ):
            self.assertEqual(production_monitoring_check(None), [])


class BrevoAPIBackendTests(TestCase):
    """core.email_backend.BrevoAPIBackend — the SMTP replacement. Exercised
    directly (not through django.core.mail.send_mail) since Django's test
    runner always overrides EMAIL_BACKEND to the locmem backend during
    tests — see core/tests.py's other email tests (mail.outbox) for that
    path; this class is what actually proves the Brevo integration itself
    is correct."""

    def _message(self, **overrides):
        from django.core.mail import EmailMessage
        kwargs = dict(
            subject='Verify your email',
            body='Click the link: https://example.com/verify?token=abc',
            from_email='noreply@example.com',
            to=['player@example.com'],
        )
        kwargs.update(overrides)
        return EmailMessage(**kwargs)

    @patch('core.email_backend.requests.post')
    def test_sends_correct_payload_and_headers(self, mock_post):
        mock_post.return_value.status_code = 201
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend()
        backend.api_key = 'test-api-key'
        sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 1)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['headers']['api-key'], 'test-api-key')
        self.assertEqual(kwargs['json']['sender'], {'email': 'noreply@example.com'})
        self.assertEqual(kwargs['json']['to'], [{'email': 'player@example.com'}])
        self.assertEqual(kwargs['json']['subject'], 'Verify your email')
        self.assertEqual(kwargs['json']['textContent'], 'Click the link: https://example.com/verify?token=abc')

    @patch('core.email_backend.requests.post')
    def test_parses_display_name_in_from_email(self, mock_post):
        mock_post.return_value.status_code = 201
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend()
        backend.api_key = 'test-api-key'
        backend.send_messages([self._message(from_email='Esports Pakistan <noreply@example.com>')])

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['sender'], {'email': 'noreply@example.com', 'name': 'Esports Pakistan'})

    @patch('core.email_backend.requests.post')
    def test_api_error_raises_by_default(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = '{"code":"invalid_parameter","message":"bad sender"}'
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend()
        backend.api_key = 'test-api-key'
        with self.assertRaises(Exception):
            backend.send_messages([self._message()])

    @patch('core.email_backend.requests.post')
    def test_api_error_swallowed_when_fail_silently(self, mock_post):
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = 'internal error'
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend(fail_silently=True)
        backend.api_key = 'test-api-key'
        sent = backend.send_messages([self._message()])
        self.assertEqual(sent, 0)

    def test_missing_api_key_raises_by_default(self):
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend()
        backend.api_key = ''
        with self.assertRaises(ValueError):
            backend.send_messages([self._message()])

    def test_missing_api_key_swallowed_when_fail_silently(self):
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend(fail_silently=True)
        backend.api_key = ''
        sent = backend.send_messages([self._message()])
        self.assertEqual(sent, 0)

    @patch('core.email_backend.requests.post')
    def test_no_messages_is_a_noop(self, mock_post):
        from core.email_backend import BrevoAPIBackend

        backend = BrevoAPIBackend()
        backend.api_key = 'test-api-key'
        self.assertEqual(backend.send_messages([]), 0)
        mock_post.assert_not_called()
