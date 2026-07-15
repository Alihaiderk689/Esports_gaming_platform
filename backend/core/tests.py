from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

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
