from django.conf import settings
from django.db import models


class Organizer(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name='organizer_profile', on_delete=models.CASCADE,
    )
    company_name = models.CharField(max_length=200)
    company_registration_number = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)

    cnic_number = models.CharField(max_length=20, blank=True)
    cnic_document = models.FileField(upload_to='organizer/cnic/%Y/%m/', blank=True, null=True)
    company_document = models.FileField(upload_to='organizer/company/%Y/%m/', blank=True, null=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.company_name} ({self.user.email})'
