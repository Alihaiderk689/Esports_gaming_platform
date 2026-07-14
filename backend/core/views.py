from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.emails import send_password_reset_email, send_verification_email
from core.serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)
from core.tokens import email_verification_token, password_reset_token

User = get_user_model()


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({'status': 'ok'})


def _decode_uid(uid):
    try:
        return force_str(urlsafe_base64_decode(uid))
    except (TypeError, ValueError, OverflowError):
        return None


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_verification_email(user)
        return Response(
            {
                'user': ProfileSerializer(user).data,
                'detail': 'Registration successful. Check your email to verify your account.',
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = 'login'


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            payload = google_id_token.verify_oauth2_token(
                serializer.validated_data['id_token'],
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            raise ValidationError({'id_token': 'Invalid Google token.'})

        email = payload.get('email')
        google_id = payload.get('sub')
        if not email or not google_id:
            raise ValidationError({'id_token': 'Google token missing required claims.'})

        user, created = User.objects.get_or_create(
            email=User.objects.normalize_email(email),
            defaults={
                'google_id': google_id,
                'first_name': payload.get('given_name', ''),
                'last_name': payload.get('family_name', ''),
                'is_email_verified': True,
            },
        )
        if not created and not user.google_id:
            user.google_id = google_id
            user.is_email_verified = True
            user.save(update_fields=['google_id', 'is_email_verified'])

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': ProfileSerializer(user).data,
        })


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
        except TokenError:
            raise ValidationError({'refresh': 'Invalid or expired token.'})
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email).first()
        if user:
            send_password_reset_email(user)
        return Response({'detail': 'If that email exists, a reset link has been sent.'})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user_id = _decode_uid(data['uid'])
        user = User.objects.filter(pk=user_id).first() if user_id else None
        if user is None or not password_reset_token.check_token(user, data['token']):
            raise ValidationError({'token': 'Invalid or expired reset link.'})

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        return Response({'detail': 'Password has been reset.'})


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        serializer = VerifyEmailSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user_id = _decode_uid(data['uid'])
        user = User.objects.filter(pk=user_id).first() if user_id else None
        if user is None or not email_verification_token.check_token(user, data['token']):
            raise ValidationError({'token': 'Invalid or expired verification link.'})

        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        return Response({'detail': 'Email verified.'})


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email, is_email_verified=False).first()
        if user:
            send_verification_email(user)
        return Response({'detail': 'If that email exists and is unverified, a link has been sent.'})


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        if not user.check_password(data['current_password']):
            raise ValidationError({'current_password': 'Incorrect password.'})

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        return Response({'detail': 'Password changed successfully.'})
