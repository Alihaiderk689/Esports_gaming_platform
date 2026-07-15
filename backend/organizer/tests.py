import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from organizer.models import Organizer

User = get_user_model()

_MEDIA_ROOT = tempfile.mkdtemp(prefix='organizer_test_media_')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class OrganizerApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.client.force_authenticate(user=self.user)

    def test_endpoints_require_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/organizer/register/', {'company_name': 'Acme'})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_status_before_registration_is_404(self):
        resp = self.client.get('/api/organizer/status/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_register(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'phone_number': '03001234567', 'address': 'Lahore',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['company_name'], 'Acme Esports')
        self.assertEqual(resp.data['status'], 'pending')
        self.assertTrue(Organizer.objects.filter(user=self.user).exists())

    def test_register_missing_company_name_rejected(self):
        resp = self.client.post('/api/organizer/register/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_twice_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.post('/api/organizer/register/', {'company_name': 'Acme 2'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_cnic_before_registration_is_404(self):
        cnic_file = SimpleUploadedFile('cnic.jpg', b'fake-image-bytes', content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {'cnic_document': cnic_file, 'cnic_number': '35202-1234567-1'})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_cnic(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        cnic_file = SimpleUploadedFile('cnic.jpg', b'fake-image-bytes', content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': cnic_file, 'cnic_number': '35202-1234567-1',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['cnic_uploaded'])
        self.assertEqual(resp.data['cnic_number'], '35202-1234567-1')

    def test_upload_cnic_without_file_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.post('/api/organizer/upload-cnic/', {'cnic_number': '35202-1234567-1'}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_company_document(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        company_file = SimpleUploadedFile('registration.pdf', b'fake-pdf-bytes', content_type='application/pdf')
        resp = self.client.post('/api/organizer/upload-company/', {
            'company_document': company_file, 'company_registration_number': 'REG-001',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['company_document_uploaded'])
        self.assertEqual(resp.data['company_registration_number'], 'REG-001')

    def test_status_after_registration(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.get('/api/organizer/status/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')

    def test_status_reflects_admin_approval(self):
        organizer = Organizer.objects.create(user=self.user, company_name='Acme', status=Organizer.Status.APPROVED)
        resp = self.client.get('/api/organizer/status/')
        self.assertEqual(resp.data['status'], 'approved')

    def test_patch_profile(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.patch('/api/organizer/profile/', {'company_name': 'Acme Renamed', 'address': 'Karachi'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['company_name'], 'Acme Renamed')
        self.assertEqual(resp.data['address'], 'Karachi')

    def test_patch_profile_cannot_change_status(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.patch('/api/organizer/profile/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')

    def test_dashboard_before_registration_is_404(self):
        resp = self.client.get('/api/organizer/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_dashboard(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.get('/api/organizer/dashboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['company_name'], 'Acme')
        self.assertIn('cnic_uploaded', resp.data)
        self.assertIn('company_document_uploaded', resp.data)

    def test_organizer_isolated_per_user(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        other_user = User.objects.create_user(email='other@example.com', password='StrongPass123')
        self.client.force_authenticate(user=other_user)
        resp = self.client.get('/api/organizer/status/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class AdminOrganizerApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='admin@example.com', password='StrongPass123', is_staff=True)
        self.user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.organizer = Organizer.objects.create(user=self.user, company_name='Acme Esports')

    def test_list_requires_admin(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/admin/organizers/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_requires_auth(self):
        resp = self.client.get('/api/admin/organizers/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get('/api/admin/organizers/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['company_name'], 'Acme Esports')
        self.assertEqual(results[0]['user_email'], 'organizer@example.com')

    def test_list_filter_by_status(self):
        Organizer.objects.create(
            user=User.objects.create_user(email='approved@example.com', password='StrongPass123'),
            company_name='Approved Co', status=Organizer.Status.APPROVED,
        )
        self.client.force_authenticate(user=self.admin)

        resp = self.client.get('/api/admin/organizers/', {'status': 'pending'})
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['company_name'], 'Acme Esports')

        resp = self.client.get('/api/admin/organizers/', {'status': 'approved'})
        results = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['company_name'], 'Approved Co')

    def test_retrieve_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'/api/admin/organizers/{self.organizer.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['company_name'], 'Acme Esports')

    def test_retrieve_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f'/api/admin/organizers/{self.organizer.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/organizers/{self.organizer.pk}/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'approved')
        self.organizer.refresh_from_db()
        self.assertEqual(self.organizer.status, Organizer.Status.APPROVED)

    def test_reject_with_reason(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/organizers/{self.organizer.pk}/', {
            'status': 'rejected', 'reason': 'CNIC image unreadable',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'rejected')
        self.assertEqual(resp.data['rejection_reason'], 'CNIC image unreadable')
        self.organizer.refresh_from_db()
        self.assertEqual(self.organizer.status, Organizer.Status.REJECTED)
        self.assertEqual(self.organizer.rejection_reason, 'CNIC image unreadable')

    def test_approve_clears_previous_rejection_reason(self):
        self.organizer.status = Organizer.Status.REJECTED
        self.organizer.rejection_reason = 'Bad document'
        self.organizer.save()

        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/organizers/{self.organizer.pk}/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['rejection_reason'], '')

    def test_update_forbidden_for_non_admin(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.patch(f'/api/admin/organizers/{self.organizer.pk}/', {'status': 'approved'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.organizer.refresh_from_db()
        self.assertEqual(self.organizer.status, Organizer.Status.PENDING)

    def test_invalid_status_rejected(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(f'/api/admin/organizers/{self.organizer.pk}/', {'status': 'banana'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
