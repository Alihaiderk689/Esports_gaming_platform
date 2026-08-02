from django.contrib.auth.tokens import PasswordResetTokenGenerator
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f'{user.pk}{user.is_email_verified}{timestamp}'


email_verification_token = EmailVerificationTokenGenerator()
password_reset_token = PasswordResetTokenGenerator()


def revoke_all_sessions(user):
    """Blacklist every outstanding refresh token for `user` — called on password
    change/reset so a stolen refresh token doesn't stay valid for its full
    7-day lifetime after the user secures their account. Doesn't touch the
    still-live access token (stateless, expires within the hour on its own)."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
