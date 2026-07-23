from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import Follow

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name']

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return email

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        return token

    def validate(self, attrs):
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


class VerifyEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


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


class PlayerUpdateSerializer(serializers.ModelSerializer):
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
