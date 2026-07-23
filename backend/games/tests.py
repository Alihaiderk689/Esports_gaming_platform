import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from games.models import Category, Game

User = get_user_model()

_MEDIA_ROOT = tempfile.mkdtemp(prefix='games_test_media_')


def _test_image_file(name='logo.png'):
    buf = BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buf, format='PNG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/png')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class GameApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)

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

    def test_logo_url_falls_back_to_cover_image_url(self):
        self.game.cover_image_url = 'https://example.com/valorant.jpg'
        self.game.save()
        resp = self.client.get(f'/api/games/{self.game.pk}/')
        self.assertEqual(resp.data['logo_url'], 'https://example.com/valorant.jpg')

    def test_logo_url_prefers_uploaded_logo(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/games/{self.game.pk}/', {'logo': _test_image_file()}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('logo.png', resp.data['logo_url'])
        self.assertNotIn('logo', resp.data)  # write_only

    def test_assign_categories_to_game(self):
        cat = Category.objects.create(name='Tactical Shooter')
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/games/{self.game.pk}/', {'category_ids': [cat.pk]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([c['name'] for c in resp.data['categories']], ['Tactical Shooter'])
        self.game.refresh_from_db()
        self.assertIn(cat, self.game.categories.all())


class CategoryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player2@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(
            email='admin2@example.com', password='StrongPass123', is_staff=True,
        )
        self.category = Category.objects.create(name='MOBA')
        self.client.force_authenticate(user=self.user)

    def test_list_categories_open_to_authenticated_users(self):
        resp = self.client.get('/api/games/categories/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [c['name'] for c in resp.data]
        self.assertIn('MOBA', names)

    def test_create_category_forbidden_for_non_admin(self):
        resp = self.client.post('/api/games/categories/', {'name': 'Battle Royale'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_category_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/games/categories/', {'name': 'Battle Royale'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['slug'], 'battle-royale')

    def test_delete_category_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/games/categories/{self.category.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_category_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/games/categories/{self.category.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())

    def test_deleting_category_does_not_delete_game(self):
        game = Game.objects.create(name='Dota 2')
        game.categories.add(self.category)
        self.client.force_authenticate(user=self.admin)
        self.client.delete(f'/api/games/categories/{self.category.pk}/')
        game.refresh_from_db()
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertEqual(game.categories.count(), 0)
