from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import Dispute, DisputeEvidence, Follow, PendingRegistration
from core.validators import clean_person_name, validate_document_file
from organizer.models import Organizer
from organizer.serializers import validate_payout_fields

User = get_user_model()

ORGANIZER_APPLICATION_FIELDS = [
    'company_name', 'phone_number', 'address',
    'cnic_number', 'cnic_document',
    'company_registration_number', 'company_document',
    'payout_method', 'jazzcash_number', 'bank_name', 'bank_account_title', 'bank_account_number',
]


class NameValidationMixin:
    """Shared first/last name rules for any serializer that lets a user set their
    own name — registration and later profile edits alike."""

    def validate_first_name(self, value):
        return clean_person_name(value, 'First name')

    def validate_last_name(self, value):
        return clean_person_name(value, 'Last name')


class RegisterSerializer(NameValidationMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=['user', 'organizer'], write_only=True, required=False, default='user')

    # Organizer application fields — only required/used when role == 'organizer', in which
    # case the organizer profile is created alongside the account in one step.
    company_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address = serializers.CharField(write_only=True, required=False, allow_blank=True)
    cnic_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    cnic_document = serializers.FileField(write_only=True, required=False, allow_null=True)
    company_registration_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    company_document = serializers.FileField(write_only=True, required=False, allow_null=True)
    payout_method = serializers.ChoiceField(
        choices=Organizer.PayoutMethod.choices, write_only=True, required=False, allow_blank=True,
    )
    jazzcash_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    bank_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    bank_account_title = serializers.CharField(write_only=True, required=False, allow_blank=True)
    bank_account_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'confirm_password', 'first_name', 'last_name', 'role'] + ORGANIZER_APPLICATION_FIELDS
        extra_kwargs = {
            # first_name/last_name are blank=True on the model (Google sign-in creates
            # users without going through this serializer at all), but manual
            # registration requires both.
            'first_name': {'required': True},
            'last_name': {'required': True},
            # Drop DRF's auto-added UniqueValidator (exact-match, generic message) so
            # validate_email below — case-insensitive, with our own message — is the
            # only thing that runs.
            'email': {'validators': []},
        }

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('This email is already registered.')
        return email

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        if attrs.get('role') == 'organizer':
            errors = {}
            if not attrs.get('company_name'):
                errors['company_name'] = 'This field is required to register as an organizer.'
            if not attrs.get('cnic_document'):
                errors['cnic_document'] = 'Please upload your CNIC document.'
            if not attrs.get('company_document'):
                errors['company_document'] = 'Please upload a company document.'
            if errors:
                raise serializers.ValidationError(errors)
            validate_payout_fields(attrs)
        return attrs

    def create(self, validated_data):
        # No User (or Organizer) is created here — only a PendingRegistration.
        # The real account only comes into existence when the emailed link is
        # verified (VerifyEmailView), so an unconfirmed/fake email never
        # results in a usable account. update_or_create keyed on email means
        # re-registering the same address before verifying just refreshes
        # this row instead of erroring — friendlier than making someone wait
        # out a token or hunt for "resend" if the first email didn't arrive.
        validated_data.pop('confirm_password')
        role = validated_data.pop('role', 'user')
        password = validated_data.pop('password')
        organizer_data = {
            field: validated_data.pop(field) for field in ORGANIZER_APPLICATION_FIELDS if field in validated_data
        }
        pending, _ = PendingRegistration.objects.update_or_create(
            email=validated_data['email'],
            defaults={
                'password_hash': make_password(password),
                'first_name': validated_data['first_name'],
                'last_name': validated_data['last_name'],
                'role': role,
                **organizer_data,
            },
        )
        return pending


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        return token

    def validate(self, attrs):
        # Registration stores emails trimmed + lowercased; normalize the login
        # attempt the same way so a different casing at login doesn't fail auth.
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        data = super().validate(attrs)
        data['user'] = ProfileSerializer(self.user).data
        return data


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    # Round-tripped through Google's own `state` param and back — see
    # core.views.GoogleOAuthStartView/GoogleLoginView for why this is what
    # makes the nonce check server-verifiable instead of client-side-only.
    state = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'is_email_verified', 'is_staff', 'is_superuser', 'date_joined',
        ]
        read_only_fields = [
            'id', 'email', 'is_email_verified', 'is_staff', 'is_superuser', 'date_joined',
        ]


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(r'^\d{6}$', error_messages={'invalid': 'Enter the 6-digit verification code.'})


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class PlayerSerializer(serializers.ModelSerializer):
    followers_count = serializers.IntegerField(read_only=True)
    following_count = serializers.IntegerField(read_only=True)
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'date_joined',
            'followers_count', 'following_count', 'is_following',
        ]
        read_only_fields = fields

    def get_is_following(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or request.user.pk == obj.pk:
            return False
        return Follow.objects.filter(follower=request.user, following=obj).exists()


class PlayerUpdateSerializer(NameValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']


class AdminUserSerializer(serializers.ModelSerializer):
    signed_up_with_google = serializers.SerializerMethodField()
    is_organizer = serializers.SerializerMethodField()
    organizer_status = serializers.SerializerMethodField()
    organizer_company_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'is_active', 'is_staff',
            'is_superuser', 'is_email_verified', 'date_joined', 'last_login',
            'signed_up_with_google', 'is_organizer', 'organizer_status', 'organizer_company_name',
        ]
        read_only_fields = [
            'id', 'email', 'first_name', 'last_name', 'is_superuser',
            'is_email_verified', 'date_joined', 'last_login',
        ]

    def get_signed_up_with_google(self, obj):
        return bool(obj.google_id)

    def get_is_organizer(self, obj):
        return getattr(obj, 'organizer_profile', None) is not None

    def get_organizer_status(self, obj):
        organizer = getattr(obj, 'organizer_profile', None)
        return organizer.status if organizer else None

    def get_organizer_company_name(self, obj):
        organizer = getattr(obj, 'organizer_profile', None)
        return organizer.company_name if organizer else None


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['is_active', 'is_staff']


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = DisputeEvidence
        fields = ['id', 'file', 'uploaded_by_email', 'uploaded_at']
        read_only_fields = fields


class DisputeSerializer(serializers.ModelSerializer):
    filed_by_email = serializers.EmailField(source='filed_by.email', read_only=True)
    resolved_by_email = serializers.EmailField(source='resolved_by.email', read_only=True)
    target_label = serializers.SerializerMethodField()
    target_tournament_id = serializers.SerializerMethodField()
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            'id', 'filed_by_email', 'target_label', 'target_tournament_id', 'description',
            'status', 'escalated_to_admin', 'escalated_at', 'resolution_notes',
            'resolved_by_email', 'resolved_at', 'created_at', 'evidence',
        ]
        read_only_fields = fields

    # Local imports, not module-level: core doesn't otherwise depend on
    # tourny_regist/brackets (they depend on core, not the reverse) — this
    # mirrors the same local-import convention used everywhere else in this
    # codebase that a lower-level app needs to read a higher-level one.
    def _is_tournament_target(self, obj):
        from tourny_regist.models import Tournament
        return obj.content_type.model_class() is Tournament

    def get_target_label(self, obj):
        if self._is_tournament_target(obj):
            return obj.target.name
        match = obj.target
        return f'{match.tournament.name} — Round {match.round_number} match'

    def get_target_tournament_id(self, obj):
        if self._is_tournament_target(obj):
            return obj.object_id
        return obj.target.tournament_id


class DisputeCreateSerializer(serializers.Serializer):
    description = serializers.CharField()

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError('A description is required.')
        return value


class DisputeStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[Dispute.Status.UNDER_REVIEW, Dispute.Status.RESOLVED, Dispute.Status.DISMISSED],
    )
    resolution_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        needs_notes = attrs['status'] in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED)
        if needs_notes and not attrs.get('resolution_notes', '').strip():
            raise serializers.ValidationError({
                'resolution_notes': 'Resolution notes are required when resolving or dismissing a dispute.',
            })
        return attrs


class DisputeEvidenceCreateSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        # ModelSerializer would run the FileField's validators= automatically;
        # this is a plain Serializer (DisputeEvidence is created manually in the
        # view, not via .save() on this serializer), so the same check the model
        # field declares is invoked explicitly here instead.
        validate_document_file(value)
        return value
