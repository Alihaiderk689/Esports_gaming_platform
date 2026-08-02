from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import Follow
from core.validators import clean_person_name
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
        validated_data.pop('confirm_password')
        role = validated_data.pop('role', 'user')
        organizer_data = {
            field: validated_data.pop(field) for field in ORGANIZER_APPLICATION_FIELDS if field in validated_data
        }
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            if role == 'organizer':
                Organizer.objects.create(user=user, **organizer_data)
        return user


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


class VerifyEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


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
