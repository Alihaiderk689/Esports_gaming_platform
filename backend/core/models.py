from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
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
