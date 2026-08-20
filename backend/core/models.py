from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.storage import CloudinarySignedStorage
from core.validators import validate_document_file


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_email_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class PendingRegistration(models.Model):
    # No User (or Organizer, for organizer signups) exists until the email
    # verification link is clicked — this holds everything submitted at
    # /api/auth/register/ time until then, so an unverified/fake email never
    # results in a usable account. See core/views.py's VerifyEmailView for
    # where this gets converted into the real User/Organizer rows.
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, default='user')

    company_name = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    cnic_number = models.CharField(max_length=20, blank=True)
    cnic_document = models.FileField(
        upload_to='organizer/cnic/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    company_registration_number = models.CharField(max_length=100, blank=True)
    company_document = models.FileField(
        upload_to='organizer/company/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    payout_method = models.CharField(max_length=10, blank=True)
    jazzcash_number = models.CharField(max_length=30, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class Follow(models.Model):
    follower = models.ForeignKey(User, related_name='following', on_delete=models.CASCADE)
    following = models.ForeignKey(User, related_name='followers', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['follower', 'following'], name='unique_follow'),
            models.CheckConstraint(check=~models.Q(follower=models.F('following')), name='no_self_follow'),
        ]

    def __str__(self):
        return f'{self.follower_id} -> {self.following_id}'


class AuditLog(models.Model):
    """Generic actor/action/target audit trail, reusable across apps via
    GenericForeignKey rather than one bespoke history model per feature.
    Write through core.audit.log_action() rather than constructing directly."""
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='audit_logs',
    )
    action = models.CharField(max_length=64)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['action']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'{self.action} by {self.actor_id} on {self.content_type_id}:{self.object_id}'

    def save(self, *args, **kwargs):
        # Append-only at the model layer, not just "nothing currently calls
        # .save() on an existing row" — this is the backstop if a future
        # admin registration or endpoint ever tries to edit history instead
        # of writing a new entry via core.audit.log_action().
        if self.pk is not None:
            raise ValueError('AuditLog entries are append-only and cannot be modified.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('AuditLog entries are append-only and cannot be deleted.')


class AdminReviewRequest(models.Model):
    """An organizer action too dangerous for self-service (e.g. cancelling a
    tournament with live registrations) routes here instead of executing
    directly. Approval doesn't replay the action generically — each
    request_type is handled by an explicit branch in the deciding view, which
    calls the same service function the safe self-service path would have
    called. See tourny_regist.lifecycle.cancel_tournament."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class RequestType(models.TextChoices):
        TOURNAMENT_CANCELLATION = 'tournament_cancellation', 'Tournament Cancellation'
        REGISTRATION_CANCELLATION = 'registration_cancellation', 'Registration Cancellation'
        BRACKET_RESET = 'bracket_reset', 'Bracket Reset'

    # SET_NULL, not CASCADE: this is a decision record (approved/rejected,
    # by whom, why) other stakeholders rely on — matches decided_by below.
    # CASCADE would delete an already-decided review's entire history the
    # moment the organizer who originally requested it deletes their account.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='review_requests',
    )
    request_type = models.CharField(max_length=40, choices=RequestType.choices)
    reason = models.TextField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['request_type', 'status']),
        ]
        constraints = [
            # At most one PENDING request per (target, request_type) — not a
            # security boundary (cancel_tournament/cancel_registration/
            # reset_bracket all re-lock and re-check current state at
            # approval time regardless of how many stale requests exist), but
            # without this, retrying a "cancel" click that appears to hang
            # queues up duplicate reviews for the same admin to work through,
            # all but one of which will 400 on approval anyway.
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'request_type'],
                condition=models.Q(status='pending'),
                name='unique_pending_review_request_per_target_and_type',
            ),
        ]

    def __str__(self):
        return f'{self.request_type} #{self.pk} ({self.status})'


class Dispute(models.Model):
    """A player/team's formal objection about a tournament or a specific match —
    a result they believe is wrong, a rules violation, conduct, etc. `target` is a
    Tournament (a general complaint) or a brackets.Match (result-specific);
    GenericForeignKey here, exactly like AuditLog/AdminReviewRequest above, is what
    lets this model live in core without importing either tourny_regist or brackets
    — both of those apps' views create/query Dispute via local imports instead,
    the same convention used everywhere else this codebase crosses an app boundary.

    Resolution is normally the tournament's own organizer (or any staff member) —
    IsTournamentStaffOrAdmin's usual "staff always passes, else must own this
    tournament" check. escalated_to_admin exists for the case that check doesn't
    cover: a dispute *about* the organizer's own ruling, where letting that same
    organizer resolve it is a conflict of interest. Once escalated, resolution is
    staff-only regardless of who organizes the tournament — see
    core.views.DisputeStatusView."""
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        UNDER_REVIEW = 'under_review', 'Under Review'
        RESOLVED = 'resolved', 'Resolved'
        DISMISSED = 'dismissed', 'Dismissed'

    # SET_NULL, not CASCADE: a dispute (and its resolution) is evidence other
    # stakeholders — the opposing player, the organizer, staff — rely on.
    # CASCADE would delete the whole dispute (and, via DisputeEvidence's own
    # FK, all its evidence) the moment whoever filed it deletes their account.
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='disputes_filed',
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    escalated_to_admin = models.BooleanField(default=False)
    escalated_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'Dispute #{self.pk} ({self.status})'


class DisputeEvidence(models.Model):
    """A single uploaded file attached to a Dispute — screenshots, recordings,
    chat logs. Same validate_document_file (size + magic-byte) check every other
    user-uploaded document in this codebase goes through; no new validation
    scheme invented for this one."""
    dispute = models.ForeignKey(Dispute, related_name='evidence', on_delete=models.CASCADE)
    file = models.FileField(upload_to='disputes/evidence/%Y/%m/', validators=[validate_document_file])
    # SET_NULL, not CASCADE — same reasoning as Dispute.filed_by just above:
    # evidence a dispute was actually resolved on shouldn't vanish because
    # whoever uploaded it (either party, not necessarily the filer) later
    # deletes their account.
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Evidence for dispute #{self.dispute_id}'
