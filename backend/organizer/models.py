from django.conf import settings
from django.db import models

from core.storage import CloudinarySignedStorage
from core.validators import (
    validate_bank_account_number,
    validate_cnic_number,
    validate_document_file,
    validate_phone_number,
    validate_pk_mobile_number,
)


class Organizer(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class PayoutMethod(models.TextChoices):
        JAZZCASH = 'jazzcash', 'JazzCash'
        BANK = 'bank', 'Bank Account'

    # PROTECT, not CASCADE: an approved organizer can self-delete their
    # account via PlayerMeView (core/views.py) like any other user, and
    # CASCADE here would silently take every tournament they've ever run —
    # and everything downstream of those (registrations, brackets, matches,
    # disputes) for every *other* player who participated — down with it.
    # Django refuses the delete instead; core.views.PlayerMeView.destroy()
    # turns that into a clear 400 rather than a bare 500.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name='organizer_profile', on_delete=models.PROTECT,
    )
    company_name = models.CharField(max_length=200)
    company_registration_number = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=30, blank=True, validators=[validate_phone_number])
    address = models.CharField(max_length=255, blank=True)

    cnic_number = models.CharField(max_length=20, blank=True, validators=[validate_cnic_number])
    cnic_document = models.FileField(
        upload_to='organizer/cnic/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    company_document = models.FileField(
        upload_to='organizer/company/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )

    payout_method = models.CharField(max_length=10, choices=PayoutMethod.choices, blank=True)
    jazzcash_number = models.CharField(max_length=30, blank=True, validators=[validate_pk_mobile_number])
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True, validators=[validate_bank_account_number])

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    last_seen_status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.company_name} ({self.user.email})'
