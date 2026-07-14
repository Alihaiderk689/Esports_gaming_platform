from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.tokens import email_verification_token, password_reset_token


def _uid_for(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def send_verification_email(user):
    uid = _uid_for(user)
    token = email_verification_token.make_token(user)
    link = f'{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}'
    send_mail(
        subject='Verify your email',
        message=f'Click the link to verify your email: {link}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
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
