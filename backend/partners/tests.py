from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from partners.models import Partner

User = get_user_model()


class PartnerApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.admin = User.objects.create_user(
            email='admin@example.com', password='StrongPass123', is_staff=True,
        )
        self.partner = Partner.objects.create(name='Red Bull', website_url='https://redbull.com')
        self.client.force_authenticate(user=self.user)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_list_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/partners/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_partners(self):
        resp = self.client.get('/api/partners/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = {p['name'] for p in self._results(resp)}
        self.assertIn('Red Bull', names)

    def test_create_forbidden_for_non_admin(self):
        resp = self.client.post('/api/partners/', {'name': 'Logitech'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/partners/', {'name': 'Logitech', 'website_url': 'https://logitechg.com'})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Partner.objects.filter(name='Logitech').exists())

    def test_create_duplicate_name_rejected(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/api/partners/', {'name': 'Red Bull'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_forbidden_for_non_admin(self):
        resp = self.client.patch(f'/api/partners/{self.partner.pk}/', {'display_order': 5})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/partners/{self.partner.pk}/', {'is_active': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.partner.refresh_from_db()
        self.assertFalse(self.partner.is_active)

    def test_delete_forbidden_for_non_admin(self):
        resp = self.client.delete(f'/api/partners/{self.partner.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Partner.objects.filter(pk=self.partner.pk).exists())

    def test_delete_allowed_for_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f'/api/partners/{self.partner.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Partner.objects.filter(pk=self.partner.pk).exists())

    def test_no_retrieve_endpoint(self):
        resp = self.client.get(f'/api/partners/{self.partner.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
