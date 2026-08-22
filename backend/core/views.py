import logging

import cloudinary.utils
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, ProtectedError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
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
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.audit import log_action
from core.emails import send_password_reset_email, send_verification_email
from core.models import Dispute, DisputeEvidence, Follow, PendingRegistration
from core.otp import OtpVerificationError, can_resend, verify_otp
from core.security_events import log_security_event
from core.serializers import (
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    DisputeCreateSerializer,
    DisputeEvidenceCreateSerializer,
    DisputeEvidenceSerializer,
    DisputeSerializer,
    DisputeStatusSerializer,
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
    VerifyOtpSerializer,
)
from core.storage import CloudinarySignedStorage
from core.throttling import EmailActionEmailRateThrottle, LoginEmailRateThrottle
from core.tokens import password_reset_token, revoke_all_sessions

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
            detail = 'Enter the verification code we emailed you to finish creating your account.'
        except Exception:
            logger.exception('Failed to send verification email for pending registration %s', pending.pk)
            detail = (
                "We couldn't send the verification code right now. "
                "Use \"Resend code\" from the sign-in page once you're ready to try again."
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
    # ScopedRateThrottle (keyed by client IP, via throttle_scope above) plus
    # LoginEmailRateThrottle (keyed by the submitted email) — layered so a
    # credential-stuffing attempt spread across many IPs still hits a ceiling
    # tied to the one account being targeted. User/AnonRateThrottle are the
    # global floors from DEFAULT_THROTTLE_CLASSES; restated here because
    # setting throttle_classes on a view replaces the default list entirely.
    throttle_classes = [ScopedRateThrottle, LoginEmailRateThrottle, UserRateThrottle, AnonRateThrottle]


class GoogleAuthUnavailable(APIException):
    """A ValueError from verify_oauth2_token means the token itself is bad
    (expired, wrong audience, malformed) — a genuine 400. A GoogleAuthError
    (e.g. TransportError) means we couldn't even reach Google to check —
    that's not the user's fault, so it gets its own 503 instead of implying
    their token was invalid."""

    status_code = 503
    default_detail = 'Could not verify with Google right now. Please try again.'
    default_code = 'service_unavailable'


GOOGLE_OAUTH_STATE_SALT = 'google-oauth-state'
# Long enough to cover the redirect round trip through Google's own login UI
# (including "choose an account"/2FA prompts), short enough to bound how long
# a captured (state, id_token) pair stays replayable if it ever leaked.
GOOGLE_OAUTH_STATE_MAX_AGE = 300


class GoogleOAuthStartView(APIView):
    """Mints a server-generated nonce and hands it back signed as `state` —
    the frontend embeds the nonce (returned in the id_token's own `nonce`
    claim by Google) and state (echoed back verbatim by Google) as the
    `nonce`/`state` params on the Google authorization URL. GoogleLoginView
    then re-derives the *expected* nonce from `state` itself and checks it
    against the token's claim server-side, rather than trusting whatever
    nonce the client says it used (the previous design: correct-looking, but
    a client-side-only check can't actually prove the token was minted for
    *this* login attempt, since it just as easily accepts one the client
    fabricated the "expected" side of). See docs/SECURITY.md#google-oauth."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        nonce = get_random_string(32)
        state = signing.TimestampSigner(salt=GOOGLE_OAUTH_STATE_SALT).sign(nonce)
        return Response({'nonce': nonce, 'state': state})


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = serializer.validated_data['state']

        signer = signing.TimestampSigner(salt=GOOGLE_OAUTH_STATE_SALT)
        try:
            expected_nonce = signer.unsign(state, max_age=GOOGLE_OAUTH_STATE_MAX_AGE)
        except signing.SignatureExpired:
            raise ValidationError({'state': 'This sign-in attempt has expired. Please try again.'})
        except signing.BadSignature:
            raise ValidationError({'state': 'Invalid sign-in attempt.'})

        # Single-use: a (state, id_token) pair that already completed a login
        # can't be replayed to log in again — closes the window
        # GOOGLE_OAUTH_STATE_MAX_AGE would otherwise leave open for a
        # captured pair to be resubmitted more than once.
        used_key = f'google_oauth_state_used:{state}'
        if cache.get(used_key):
            raise ValidationError({'state': 'This sign-in attempt has already been used.'})

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
            log_security_event('google_login.invalid_token', request=request)
            raise ValidationError({'id_token': 'Invalid Google token.'})
        except GoogleAuthError:
            logger.exception('Failed to reach Google while verifying an id_token')
            raise GoogleAuthUnavailable()

        if payload.get('nonce') != expected_nonce:
            # Doesn't happen from the normal frontend flow (Google embeds
            # whatever `nonce` param it was given, and that's exactly what
            # `state` was signed from) — this only fires if the id_token
            # being presented wasn't obtained using this state at all.
            log_security_event('google_login.nonce_mismatch', request=request)
            raise ValidationError({'id_token': 'Google sign-in failed a security check. Please try again.'})

        email = payload.get('email')
        google_id = payload.get('sub')
        if not email or not google_id:
            raise ValidationError({'id_token': 'Google token missing required claims.'})
        if not payload.get('email_verified'):
            # Google issues this claim to distinguish "this account controls this
            # email" from "this email is merely on file" — trusting an unverified
            # email would let someone log into (or silently create) an account
            # for an address they don't actually control.
            log_security_event('google_login.unverified_email', request=request, attempted_email=email)
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
        newly_linked = not created and not user.google_id
        if newly_linked:
            user.google_id = google_id
            user.is_email_verified = True
            user.save(update_fields=['google_id', 'is_email_verified'])

        # Marked used only on the success path — a Google-unreachable 503 or
        # a client-side retry after some other transient failure can still
        # complete with the same (state, id_token) pair; it's *successful*
        # logins this guards against being replayed.
        cache.set(used_key, True, timeout=GOOGLE_OAUTH_STATE_MAX_AGE)
        log_security_event(
            'google_login.success', request=request, target_user_id=user.pk,
            account_created=created, linked_existing_account=newly_linked,
        )

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


class LogoutAllSessionsView(APIView):
    """Deliberately exposes core.tokens.revoke_all_sessions — previously only
    called internally on password change/reset — as its own self-service
    action, for a user who suspects a device/browser they're not holding
    right now still has a valid refresh token (a shared computer, a stolen
    laptop, ...). Blacklists every outstanding refresh token for the caller;
    the access token that made *this* request stays valid until it expires
    on its own (same tradeoff as password change/reset — see
    core.tokens.revoke_all_sessions's docstring)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        revoke_all_sessions(request.user)
        log_security_event('session.logout_all', request=request)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'
    # See LoginView: per-account throttle layered on the IP-scoped one so an
    # attacker can't email-bomb one victim's inbox with reset links from many
    # different IPs.
    throttle_classes = [ScopedRateThrottle, EmailActionEmailRateThrottle, UserRateThrottle, AnonRateThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email).first()
        if user:
            log_security_event('password_reset.requested', request=request, target_user_id=user.pk)
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
            log_security_event('password_reset.invalid_token', request=request, target_user_id=user_id)
            raise ValidationError({'token': 'Invalid or expired reset link.'})

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        revoke_all_sessions(user)
        log_security_event('password_reset.completed', request=request, target_user_id=user.pk)
        return Response({'detail': 'Password has been reset.'})


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'
    # A 6-digit code is brute-forceable in a way a 128-bit link token never
    # was — layer the per-email throttle on top of the per-IP one (see
    # ForgotPasswordView) in addition to otp_attempts' own lockout below.
    throttle_classes = [ScopedRateThrottle, EmailActionEmailRateThrottle, UserRateThrottle, AnonRateThrottle]

    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        code = serializer.validated_data['otp']

        pending = PendingRegistration.objects.filter(email__iexact=email).first()
        if pending is None:
            # Same generic error as a wrong/expired/locked code — doesn't
            # reveal whether a pending registration exists for this email.
            log_security_event('email_verification.failed', request=request, reason='no_pending_registration')
            raise ValidationError({'otp': 'Invalid or expired code.'})

        try:
            verify_otp(pending, code)
        except OtpVerificationError as exc:
            log_security_event(
                'email_verification.failed', request=request,
                target_pending_id=pending.pk, reason=exc.message,
            )
            detail = {'otp': exc.message}
            if exc.attempts_remaining is not None:
                detail['attempts_remaining'] = exc.attempts_remaining
            raise ValidationError(detail)

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

        log_security_event('email_verification.completed', request=request, target_user_id=user.pk)
        return Response({'detail': 'Account created and email verified. You can sign in now.'})


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'email_action'
    # See ForgotPasswordView.
    throttle_classes = [ScopedRateThrottle, EmailActionEmailRateThrottle, UserRateThrottle, AnonRateThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        pending = PendingRegistration.objects.filter(email__iexact=email).first()
        # can_resend enforces a cooldown independent of the hourly throttle
        # above — the response stays generic either way, so this never
        # reveals whether the email exists or is merely on cooldown.
        if pending and can_resend(pending):
            try:
                send_verification_email(pending)
            except Exception:
                logger.exception('Failed to send verification email for pending registration %s', pending.pk)
        return Response({'detail': 'If that email exists and is unverified, a new code has been sent.'})


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


class ProtectedUserDeleteMixin:
    """Organizer.user is PROTECT (see that model) specifically so deleting a
    User can't silently cascade into deleting every tournament — and
    everything downstream of those for every other participant — the
    account ever organized. Surfaces that as a clear 400 instead of an
    unhandled 500 from ProtectedError, for every path a User row can be
    deleted through (self-service and admin-initiated alike)."""

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                'detail': (
                    'This account has an organizer profile with tournaments on record and '
                    'cannot be deleted. Contact support if you need to close this account.'
                ),
            })


class PlayerDetailView(ProtectedUserDeleteMixin, generics.RetrieveUpdateDestroyAPIView):
    """Read access for any authenticated player; writes are admin-only (self-service lives at /players/me/)."""
    queryset = _players_queryset()
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return PlayerUpdateSerializer
        return PlayerSerializer


class PlayerMeView(ProtectedUserDeleteMixin, generics.RetrieveUpdateDestroyAPIView):
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

        changing_staff_status = 'is_staff' in request.data or 'is_active' in request.data
        if changing_staff_status:
            # Re-authentication for the single most consequential admin
            # action this endpoint exposes: granting/revoking someone else's
            # staff access. A compromised-but-still-logged-in admin session
            # (stolen access token, unattended browser) shouldn't be able to
            # mint a second admin account or deactivate one on its own — this
            # doesn't require a *recent* login, just proof the caller still
            # knows the admin's own password right now.
            current_password = request.data.get('current_password')
            if not current_password or not request.user.check_password(current_password):
                log_security_event(
                    'admin.staff_status_change.reauth_failed', request=request, target_user_id=instance.pk,
                )
                raise ValidationError({'current_password': 'Re-enter your password to change staff access.'})

        before_is_staff, before_is_active = instance.is_staff, instance.is_active
        super().update(request, *args, **kwargs)

        if changing_staff_status:
            instance.refresh_from_db()
            log_action(
                request.user, 'admin.user_staff_status_changed', instance,
                before={'is_staff': before_is_staff, 'is_active': before_is_active},
                after={'is_staff': instance.is_staff, 'is_active': instance.is_active},
            )
            log_security_event(
                'admin.staff_status_change.success', request=request, target_user_id=instance.pk,
                is_staff=instance.is_staff, is_active=instance.is_active,
            )
        return Response(AdminUserSerializer(self.get_object()).data)


def _dispute_tournament(dispute):
    """The Tournament that governs a dispute regardless of whether it targets
    the Tournament directly or a specific brackets.Match — see Dispute's own
    docstring for why this is a local import."""
    from tourny_regist.models import Tournament
    if dispute.content_type.model_class() is Tournament:
        return dispute.target
    return dispute.target.tournament


def _can_manage_dispute(user, dispute):
    """Staff always may. The tournament's own organizer may too — unless the
    dispute has been escalated, at which point resolving it is staff-only (see
    Dispute.escalated_to_admin's docstring: the whole point of escalation is
    taking that decision out of the organizer's hands)."""
    if user.is_staff:
        return True
    if dispute.escalated_to_admin:
        return False
    organizer_profile = getattr(user, 'organizer_profile', None)
    return organizer_profile is not None and _dispute_tournament(dispute).organizer_id == organizer_profile.pk


def _is_dispute_stakeholder(user, dispute):
    return dispute.filed_by_id == user.pk or _can_manage_dispute(user, dispute)


class DisputeMineView(generics.ListAPIView):
    """Disputes the current user personally filed — the self-service tracking
    view a player uses, as distinct from the tournament-scoped list organizers
    and staff see."""
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Dispute.objects.filter(filed_by=self.request.user).select_related(
            'filed_by', 'resolved_by', 'content_type',
        ).prefetch_related('evidence').order_by('-created_at')


class DisputeDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        dispute = get_object_or_404(
            Dispute.objects.select_related('filed_by', 'resolved_by', 'content_type').prefetch_related('evidence'),
            pk=pk,
        )
        if not _is_dispute_stakeholder(request.user, dispute):
            raise NotFound()
        return Response(DisputeSerializer(dispute, context={'request': request}).data)


class DisputeEvidenceUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        dispute = get_object_or_404(Dispute, pk=pk)
        if not _is_dispute_stakeholder(request.user, dispute):
            raise NotFound()
        # Mirrors DisputeStatusView's identical check — a dispute's decision
        # is final once resolved/dismissed; evidence attached afterward
        # wouldn't be considered by anything and would misleadingly suggest
        # the record is still open to new input.
        if dispute.status in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED):
            raise ValidationError({'detail': f'This dispute is already {dispute.status} and no longer accepts evidence.'})

        serializer = DisputeEvidenceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evidence = DisputeEvidence.objects.create(
            dispute=dispute, uploaded_by=request.user, file=serializer.validated_data['file'],
        )
        return Response(DisputeEvidenceSerializer(evidence, context={'request': request}).data, status=status.HTTP_201_CREATED)


class DisputeStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        dispute = get_object_or_404(Dispute, pk=pk)
        if not _can_manage_dispute(request.user, dispute):
            raise PermissionDenied()
        if dispute.status in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED):
            raise ValidationError({'detail': f'This dispute is already {dispute.status}.'})

        serializer = DisputeStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        dispute.status = new_status
        dispute.resolution_notes = serializer.validated_data.get('resolution_notes', '')
        if new_status in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED):
            dispute.resolved_by = request.user
            dispute.resolved_at = timezone.now()
        dispute.save(update_fields=['status', 'resolution_notes', 'resolved_by', 'resolved_at'])

        log_action(request.user, f'dispute.{new_status}', dispute, reason=dispute.resolution_notes)
        return Response(DisputeSerializer(dispute, context={'request': request}).data)


class DisputeEscalateView(APIView):
    """Lets the person who filed a dispute (or staff, proactively) take its
    resolution out of the organizer's hands — see _can_manage_dispute."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        dispute = get_object_or_404(Dispute, pk=pk)
        if not (dispute.filed_by_id == request.user.pk or request.user.is_staff):
            raise PermissionDenied()
        if dispute.escalated_to_admin:
            raise ValidationError({'detail': 'This dispute has already been escalated to admin review.'})
        if dispute.status in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED):
            raise ValidationError({'detail': f'This dispute is already {dispute.status} and cannot be escalated.'})

        dispute.escalated_to_admin = True
        dispute.escalated_at = timezone.now()
        dispute.save(update_fields=['escalated_to_admin', 'escalated_at'])
        log_action(request.user, 'dispute.escalated', dispute)
        return Response(DisputeSerializer(dispute, context={'request': request}).data)


class AdminDisputeListView(generics.ListAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Dispute.objects.select_related('filed_by', 'resolved_by', 'content_type').prefetch_related(
        'evidence',
    ).order_by('-created_at')

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        escalated_param = self.request.query_params.get('escalated')
        if escalated_param is not None:
            queryset = queryset.filter(escalated_to_admin=escalated_param.lower() in ('1', 'true'))
        return queryset
