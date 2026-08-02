from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Follow

User = get_user_model()


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
        self.assertTrue(User.objects.filter(email='newplayer@example.com').exists())

    def test_register_normalizes_email_case_and_whitespace(self):
        resp = self.client.post('/api/auth/register/', self._payload(email='  John@Example.com  '))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(User.objects.filter(email='john@example.com').exists())

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


class LoginApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='caseuser@example.com', password='StrongPass123!')

    def test_login_email_case_insensitive(self):
        resp = self.client.post('/api/auth/login/', {'email': 'CaseUser@Example.com', 'password': 'StrongPass123!'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['user']['email'], 'caseuser@example.com')


class GoogleLoginApiTests(APITestCase):
    def _payload(self, **overrides):
        payload = {
            'email': 'googleuser@example.com', 'email_verified': True,
            'sub': 'google-sub-123', 'given_name': 'Goo', 'family_name': 'Gler',
        }
        payload.update(overrides)
        return payload

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_unverified_email_rejected(self, mock_verify):
        mock_verify.return_value = self._payload(email_verified=False)
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='googleuser@example.com').exists())

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_verified_email_accepted(self, mock_verify):
        mock_verify.return_value = self._payload()
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(User.objects.filter(email='googleuser@example.com').exists())

    @patch('core.views.google_id_token.verify_oauth2_token')
    def test_google_login_network_failure_returns_503_not_400(self, mock_verify):
        from google.auth.exceptions import TransportError

        mock_verify.side_effect = TransportError('could not reach Google')
        resp = self.client.post('/api/auth/google-login/', {'id_token': 'fake-token'})
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, resp.data)
        self.assertFalse(User.objects.filter(email='googleuser@example.com').exists())


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
