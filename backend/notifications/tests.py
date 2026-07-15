from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import Notification

User = get_user_model()


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='player@example.com', password='StrongPass123')
        self.other_user = User.objects.create_user(email='other@example.com', password='StrongPass123')
        self.n1 = Notification.objects.create(recipient=self.user, title='Match starting soon')
        self.n2 = Notification.objects.create(recipient=self.user, title='Organizer application approved')
        self.other_notification = Notification.objects.create(recipient=self.other_user, title='Not yours')
        self.client.force_authenticate(user=self.user)

    def _results(self, resp):
        return resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data

    def test_list_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/notifications/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_only_own_notifications(self):
        resp = self.client.get('/api/notifications/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = {n['title'] for n in self._results(resp)}
        self.assertEqual(titles, {'Match starting soon', 'Organizer application approved'})

    def test_mark_read(self):
        resp = self.client.patch('/api/notifications/read/', {'ids': [self.n1.pk]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['updated'], 1)
        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertFalse(self.n2.is_read)

    def test_mark_read_cannot_touch_others_notifications(self):
        resp = self.client.patch('/api/notifications/read/', {'ids': [self.other_notification.pk]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['updated'], 0)
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_mark_read_empty_ids_rejected(self):
        resp = self.client.patch('/api/notifications/read/', {'ids': []})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mark_read_missing_ids_rejected(self):
        resp = self.client.patch('/api/notifications/read/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mark_all_read(self):
        resp = self.client.patch('/api/notifications/read-all/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['updated'], 2)
        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertTrue(self.n2.is_read)

    def test_mark_all_read_does_not_affect_other_users(self):
        self.client.patch('/api/notifications/read-all/')
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_mark_all_read_only_updates_unread(self):
        self.n1.is_read = True
        self.n1.save()
        resp = self.client.patch('/api/notifications/read-all/')
        self.assertEqual(resp.data['updated'], 1)

    def test_delete_own_notification(self):
        resp = self.client.delete(f'/api/notifications/{self.n1.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=self.n1.pk).exists())

    def test_delete_other_users_notification_forbidden(self):
        resp = self.client.delete(f'/api/notifications/{self.other_notification.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Notification.objects.filter(pk=self.other_notification.pk).exists())

    def test_delete_nonexistent_notification(self):
        resp = self.client.delete('/api/notifications/999999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
