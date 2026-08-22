from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.otp import OTP_TTL, issue_otp
from core.tokens import password_reset_token


def _uid_for(obj):
    return urlsafe_base64_encode(force_bytes(obj.pk))


def send_verification_email(pending_registration):
    otp = issue_otp(pending_registration)
    minutes = int(OTP_TTL.total_seconds() // 60)
    send_mail(
        subject='Your Esports Pakistan verification code',
        message=(
            f'Your verification code is: {otp}\n\n'
            f'Enter this code to finish creating your account. It expires in {minutes} minutes.\n\n'
            "If you didn't request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[pending_registration.email],
    )


def send_password_reset_email(user):
    uid = _uid_for(user)
    token = password_reset_token.make_token(user)
    link = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
    send_mail(
        subject='Reset your password',
        message=f'Click the link to reset your password: {link}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
