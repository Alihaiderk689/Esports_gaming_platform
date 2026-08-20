import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

import cloudinary.exceptions
import fitz
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from organizer.models import Organizer

User = get_user_model()

_MEDIA_ROOT = tempfile.mkdtemp(prefix='organizer_test_media_')


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


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class OrganizerApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(email='organizer@example.com', password='StrongPass123')
        self.client.force_authenticate(user=self.user)

        # cnic_document/company_document now live in Cloudinary (CloudinarySignedStorage),
        # not under MEDIA_ROOT, so @override_settings(MEDIA_ROOT=...) no longer isolates
        # them from the real account — patch the SDK calls instead of hitting the network.
        self.mock_upload = patch('cloudinary.uploader.upload').start()
        self.mock_upload.return_value = {'public_id': 'test/fake-public-id'}
        self.mock_resource = patch(
            'cloudinary.api.resource', side_effect=cloudinary.exceptions.NotFound('not found'),
        ).start()
        self.addCleanup(patch.stopall)

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
            'payout_method': 'jazzcash', 'jazzcash_number': '03001234567',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['company_name'], 'Acme Esports')
        self.assertEqual(resp.data['status'], 'pending')
        self.assertTrue(Organizer.objects.filter(user=self.user).exists())

    def test_register_invalid_phone_number_rejected(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'phone_number': 'abc', 'address': 'Lahore',
            'payout_method': 'jazzcash', 'jazzcash_number': '03001234567',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', resp.data)

    def test_register_invalid_jazzcash_number_rejected(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'payout_method': 'jazzcash', 'jazzcash_number': 'x',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('jazzcash_number', resp.data)

    def test_register_invalid_bank_account_number_rejected(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'payout_method': 'bank',
            'bank_name': 'HBL', 'bank_account_title': 'Acme', 'bank_account_number': '1',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('bank_account_number', resp.data)

    def test_register_valid_bank_account_number_accepted(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'payout_method': 'bank',
            'bank_name': 'HBL', 'bank_account_title': 'Acme', 'bank_account_number': 'PK00HABB0000000000000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_upload_cnic_invalid_format_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        cnic_file = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': cnic_file, 'cnic_number': '12345',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cnic_number', resp.data)

    def test_register_missing_company_name_rejected(self):
        resp = self.client.post('/api/organizer/register/', {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_payout_details_rejected(self):
        resp = self.client.post('/api/organizer/register/', {'company_name': 'Acme Esports'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('payout_method', resp.data)

    def test_register_bank_payout_requires_bank_details(self):
        resp = self.client.post('/api/organizer/register/', {
            'company_name': 'Acme Esports', 'payout_method': 'bank',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('bank_name', resp.data)
        self.assertIn('bank_account_title', resp.data)
        self.assertIn('bank_account_number', resp.data)

    def test_register_twice_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.post('/api/organizer/register/', {'company_name': 'Acme 2'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_cnic_before_registration_is_404(self):
        cnic_file = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {'cnic_document': cnic_file, 'cnic_number': '35202-1234567-1'})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_cnic(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        cnic_file = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': cnic_file, 'cnic_number': '35202-1234567-1',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['cnic_uploaded'])
        self.assertEqual(resp.data['cnic_number'], '35202-1234567-1')
        self.mock_upload.assert_called_once()

    def test_upload_cnic_returns_clean_error_when_cloudinary_fails(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        self.mock_upload.side_effect = Exception('simulated Cloudinary outage')
        cnic_file = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES, content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': cnic_file, 'cnic_number': '35202-1234567-1',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_upload_cnic_without_file_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        resp = self.client.post('/api/organizer/upload-cnic/', {'cnic_number': '35202-1234567-1'}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_cnic_rejects_non_image_content(self):
        """An HTML/SVG file renamed to look like a CNIC scan must be rejected by content,
        not by extension — this is what closes the stored-XSS-via-admin-preview path."""
        Organizer.objects.create(user=self.user, company_name='Acme')
        malicious = SimpleUploadedFile(
            'cnic.jpg', b'<html><script>alert(document.cookie)</script></html>', content_type='image/jpeg',
        )
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': malicious, 'cnic_number': '35202-1234567-1',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cnic_document', resp.data)
        self.mock_upload.assert_not_called()

    def test_upload_cnic_rejects_oversized_file(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        oversized = SimpleUploadedFile('cnic.jpg', _JPEG_BYTES + b'\x00' * (10 * 1024 * 1024), content_type='image/jpeg')
        resp = self.client.post('/api/organizer/upload-cnic/', {
            'cnic_document': oversized, 'cnic_number': '35202-1234567-1',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cnic_document', resp.data)
        self.mock_upload.assert_not_called()

    def test_upload_company_document(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        company_file = SimpleUploadedFile('registration.pdf', _PDF_BYTES, content_type='application/pdf')
        resp = self.client.post('/api/organizer/upload-company/', {
            'company_document': company_file, 'company_registration_number': 'REG-001',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['company_document_uploaded'])
        self.mock_upload.assert_called_once()

    def test_upload_company_document_rejects_non_pdf_content(self):
        Organizer.objects.create(user=self.user, company_name='Acme')
        malicious = SimpleUploadedFile(
            'registration.pdf', b'<svg onload="alert(1)"></svg>', content_type='application/pdf',
        )
        resp = self.client.post('/api/organizer/upload-company/', {
            'company_document': malicious, 'company_registration_number': 'REG-001',
        }, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('company_document', resp.data)
        self.mock_upload.assert_not_called()

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

    def test_resubmit_requires_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post('/api/organizer/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_resubmit_before_registration_is_404(self):
        resp = self.client.post('/api/organizer/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_resubmit_rejected_application(self):
        Organizer.objects.create(
            user=self.user, company_name='Acme',
            status=Organizer.Status.REJECTED, rejection_reason='CNIC image unreadable',
        )
        resp = self.client.post('/api/organizer/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['rejection_reason'], '')

        organizer = Organizer.objects.get(user=self.user)
        self.assertEqual(organizer.status, Organizer.Status.PENDING)
        self.assertEqual(organizer.rejection_reason, '')
        self.assertEqual(organizer.last_seen_status, Organizer.Status.PENDING)

    def test_resubmit_pending_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme', status=Organizer.Status.PENDING)
        resp = self.client.post('/api/organizer/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resubmit_approved_rejected(self):
        Organizer.objects.create(user=self.user, company_name='Acme', status=Organizer.Status.APPROVED)
        resp = self.client.post('/api/organizer/resubmit/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


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
