from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Game

User = get_user_model()


class GameApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(
            email='admin@example.com', password='StrongPass123', is_staff=True,
        )
        self.game = Game.objects.create(name='Valorant', genre='FPS', platform='PC')
        self.client.force_authenticate(user=self.user)

    def test_list_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/games/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_games(self):
        resp = self.client.get('/api/games/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        names = {g['name'] for g in results}
        self.assertIn('Valorant', names)

    def test_retrieve_game(self):
        resp = self.client.get(f'/api/games/{self.game.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], 'Valorant')
        self.assertEqual(resp.data['slug'], 'valorant')

    def test_create_forbidden_for_non_admin(self):
        resp = self.client.post('/api/games/', {'name': 'League of Legends', 'genre': 'MOBA'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/games/', {'name': 'League of Legends', 'genre': 'MOBA'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['slug'], 'league-of-legends')
        self.assertTrue(Game.objects.filter(name='League of Legends').exists())

    def test_patch_forbidden_for_non_admin(self):
        resp = self.client.patch(f'/api/games/{self.game.pk}/', {'genre': 'Tactical Shooter'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/games/{self.game.pk}/', {'genre': 'Tactical Shooter'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.game.refresh_from_db()
        self.assertEqual(self.game.genre, 'Tactical Shooter')

    def test_delete_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/games/{self.game.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Game.objects.filter(pk=self.game.pk).exists())

    def test_delete_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/games/{self.game.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Game.objects.filter(pk=self.game.pk).exists())

    def test_create_duplicate_name_rejected(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/games/', {'name': 'Valorant'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
