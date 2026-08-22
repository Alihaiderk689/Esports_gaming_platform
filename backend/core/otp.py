import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = timedelta(seconds=60)


def generate_otp():
    # secrets, not random — this is a credential a client submits back for
    # verification, same threat model as a password reset token.
    return f'{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}'


def issue_otp(pending):
    """Mints a new code, stores only its hash on `pending` (never the raw
    value), and resets the attempt counter. Returns the raw code so the
    caller can email it — once this returns, the raw code lives only in
    memory and in the recipient's inbox, never in the database or logs."""
    otp = generate_otp()
    pending.otp_hash = make_password(otp)
    pending.otp_expires_at = timezone.now() + OTP_TTL
    pending.otp_attempts = 0
    pending.otp_last_sent_at = timezone.now()
    pending.save(update_fields=['otp_hash', 'otp_expires_at', 'otp_attempts', 'otp_last_sent_at'])
    return otp


def can_resend(pending):
    if not pending.otp_last_sent_at:
        return True
    return timezone.now() >= pending.otp_last_sent_at + OTP_RESEND_COOLDOWN


class OtpVerificationError(Exception):
    def __init__(self, message, attempts_remaining=None):
        super().__init__(message)
        self.message = message
        self.attempts_remaining = attempts_remaining


def verify_otp(pending, code):
    """Raises OtpVerificationError on any failure, otherwise returns None.
    A wrong guess counts against otp_attempts; expiry and an already-spent
    attempt budget don't consume a further attempt, they just keep failing
    until the caller requests a fresh code."""
    if not pending.otp_hash or not pending.otp_expires_at:
        raise OtpVerificationError('No verification code has been requested for this email.')
    if pending.otp_attempts >= OTP_MAX_ATTEMPTS:
        raise OtpVerificationError('Too many incorrect attempts. Request a new code.')
    if timezone.now() > pending.otp_expires_at:
        raise OtpVerificationError('This code has expired. Request a new one.')
    # check_password uses a constant-time comparison internally — guards
    # against a timing attack narrowing down the code digit by digit.
    if not check_password(code, pending.otp_hash):
        pending.otp_attempts += 1
        pending.save(update_fields=['otp_attempts'])
        remaining = OTP_MAX_ATTEMPTS - pending.otp_attempts
        if remaining <= 0:
            raise OtpVerificationError('Too many incorrect attempts. Request a new code.')
        raise OtpVerificationError('Incorrect code.', attempts_remaining=remaining)
