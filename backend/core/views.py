import logging

import cloudinary.utils
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from organizer.models import Organizer
from rest_framework import filters, generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.emails import send_password_reset_email, send_verification_email
from core.models import Follow, PendingRegistration
from core.serializers import (
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    PlayerSerializer,
    PlayerUpdateSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)
from core.storage import CloudinarySignedStorage
from core.tokens import password_reset_token, pending_registration_token, revoke_all_sessions

User = get_user_model()
logger = logging.getLogger(__name__)


def _players_queryset():
    return User.objects.filter(is_active=True).annotate(
        followers_count=Count('followers', distinct=True),
        following_count=Count('following', distinct=True),
    )


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({'status': 'ok'})


@never_cache
@xframe_options_exempt
def secure_media_view(request):
    """Resolves a CloudinarySignedStorage link (see core.storage) to the file it
    points at. Our own signature — checked with a max age — is the first gate:
    links are only ever handed out by a serializer that has already run its own
    ownership/staff check, so anyone reaching this view with a valid, unexpired
    token is already authorized. Once past that gate, this mints a fresh
    Cloudinary "authenticated" signed URL (Cloudinary itself 401s without a
    matching signature — verified live) and redirects to it, so Cloudinary's
    CDN serves the actual bytes instead of proxying them through this server.

    xframe_options_exempt mirrors the previous dev-only media route: the admin
    UI previews these documents in an <iframe>.
    """
    token = request.GET.get('token', '')
    signer = signing.TimestampSigner(salt=CloudinarySignedStorage.signer_salt)
    try:
        public_id = signer.unsign(token, max_age=CloudinarySignedStorage.url_max_age)
    except signing.SignatureExpired:
        raise Http404('This link has expired.')
    except signing.BadSignature:
        raise Http404('Not found.')

    cloudinary_url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=CloudinarySignedStorage.resource_type,
        type=CloudinarySignedStorage.delivery_type,
        sign_url=True,
        secure=True,
    )
    return HttpResponseRedirect(cloudinary_url)


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
        pending = serializer.save()

        # No account exists yet at this point — just a PendingRegistration.
        # An SMTP failure here must not turn into a 500 that makes the client
        # think registration itself failed, since retrying would just refresh
        # the same pending row with no way to know the first attempt "failed"
        # for an unrelated reason. Tell them plainly and let "resend
        # verification" cover it instead.
        try:
            send_verification_email(pending)
            detail = 'Check your email to verify it and finish creating your account.'
        except Exception:
            logger.exception('Failed to send verification email for pending registration %s', pending.pk)
            detail = (
                "We couldn't send the verification email right now. "
                "Use \"Resend verification\" from the sign-in page once you're ready to try again."
            )

        if pending.role == 'organizer':
            detail += ' Once verified, your organizer application will be submitted for review.'
        return Response(
            {'detail': detail},
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = 'login'


class GoogleAuthUnavailable(APIException):
    """A ValueError from verify_oauth2_token means the token itself is bad
    (expired, wrong audience, malformed) — a genuine 400. A GoogleAuthError
    (e.g. TransportError) means we couldn't even reach Google to check —
    that's not the user's fault, so it gets its own 503 instead of implying
    their token was invalid."""

    status_code = 503
    default_detail = 'Could not verify with Google right now. Please try again.'
    default_code = 'service_unavailable'


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
        except ValueError as exc:
            # verify_oauth2_token raises plain ValueError for every distinct
            # failure mode (expired token, audience/client_id mismatch, bad
            # signature, wrong issuer, clock skew...) with no subclass to
            # distinguish them — the message text is the only place that
            # information exists. Logging it here (rather than only the
            # generic client-facing message below) is the only way to tell
            # those apart from Render's logs after the fact.
            logger.warning('Google id_token verification failed: %s', exc)
            raise ValidationError({'id_token': 'Invalid Google token.'})
        except GoogleAuthError:
            logger.exception('Failed to reach Google while verifying an id_token')
            raise GoogleAuthUnavailable()

        email = payload.get('email')
        google_id = payload.get('sub')
        if not email or not google_id:
            raise ValidationError({'id_token': 'Google token missing required claims.'})
        if not payload.get('email_verified'):
            # Google issues this claim to distinguish "this account controls this
            # email" from "this email is merely on file" — trusting an unverified
            # email would let someone log into (or silently create) an account
            # for an address they don't actually control.
            raise ValidationError({'id_token': 'Your Google account email is not verified.'})
        email = email.strip().lower()

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
            try:
                send_password_reset_email(user)
            except Exception:
                logger.exception('Failed to send password reset email to user %s', user.pk)
        return Response({'detail': 'If that email exists, a reset link has been sent.'})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'

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
        revoke_all_sessions(user)
        return Response({'detail': 'Password has been reset.'})


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'

    def get(self, request):
        serializer = VerifyEmailSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        pending_id = _decode_uid(data['uid'])
        pending = PendingRegistration.objects.filter(pk=pending_id).first() if pending_id else None
        if pending is None or not pending_registration_token.check_token(pending, data['token']):
            raise ValidationError({'token': 'Invalid or expired verification link.'})

        # This is the only place a User (and, for organizer signups, an
        # Organizer) actually gets created — everything submitted at
        # registration time has been sitting on `pending` until now.
        with transaction.atomic():
            user = User(
                email=pending.email,
                first_name=pending.first_name,
                last_name=pending.last_name,
                is_email_verified=True,
            )
            # Already hashed via make_password() when the PendingRegistration
            # was created — set directly rather than create_user()/
            # set_password(), which would hash it a second time.
            user.password = pending.password_hash
            user.save()

            if pending.role == 'organizer':
                Organizer.objects.create(
                    user=user,
                    company_name=pending.company_name,
                    phone_number=pending.phone_number,
                    address=pending.address,
                    cnic_number=pending.cnic_number,
                    cnic_document=pending.cnic_document,
                    company_registration_number=pending.company_registration_number,
                    company_document=pending.company_document,
                    payout_method=pending.payout_method,
                    jazzcash_number=pending.jazzcash_number,
                    bank_name=pending.bank_name,
                    bank_account_title=pending.bank_account_title,
                    bank_account_number=pending.bank_account_number,
                )

            pending.delete()

        return Response({'detail': 'Account created and email verified. You can sign in now.'})


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        pending = PendingRegistration.objects.filter(email__iexact=email).first()
        if pending:
            try:
                send_verification_email(pending)
            except Exception:
                logger.exception('Failed to send verification email for pending registration %s', pending.pk)
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
        revoke_all_sessions(user)
        return Response({'detail': 'Password changed successfully.'})


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class PlayerListView(generics.ListAPIView):
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = _players_queryset().order_by('-date_joined')
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'first_name', 'last_name']


class PlayerDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Read access for any authenticated player; writes are admin-only (self-service lives at /players/me/)."""
    queryset = _players_queryset()
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return PlayerUpdateSerializer
        return PlayerSerializer


class PlayerMeView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return _players_queryset().get(pk=self.request.user.pk)

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return PlayerUpdateSerializer
        return PlayerSerializer


class PlayerTopView(generics.ListAPIView):
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = _players_queryset().order_by('-followers_count', '-date_joined')


class PlayerFollowingView(generics.ListAPIView):
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        following_ids = Follow.objects.filter(follower=self.request.user).values_list('following_id', flat=True)
        return _players_queryset().filter(pk__in=following_ids).order_by('-date_joined')


class PlayerFollowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if pk == request.user.pk:
            raise ValidationError({'detail': 'You cannot follow yourself.'})
        target = get_object_or_404(User, pk=pk)

        _, created = Follow.objects.get_or_create(follower=request.user, following=target)
        if not created:
            raise ValidationError({'detail': 'You are already following this player.'})
        return Response({'detail': 'Player followed.'}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        target = get_object_or_404(User, pk=pk)

        deleted, _ = Follow.objects.filter(follower=request.user, following=target).delete()
        if not deleted:
            raise ValidationError({'detail': 'You are not following this player.'})
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.select_related('organizer_profile').order_by('-date_joined')
    filter_backends = [filters.SearchFilter]
    search_fields = ['email', 'first_name', 'last_name']


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.select_related('organizer_profile')
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pk == request.user.pk and (
            request.data.get('is_active') is False or request.data.get('is_staff') is False
        ):
            raise ValidationError({'detail': 'You cannot remove your own admin access or deactivate yourself.'})
        super().update(request, *args, **kwargs)
        return Response(AdminUserSerializer(self.get_object()).data)
