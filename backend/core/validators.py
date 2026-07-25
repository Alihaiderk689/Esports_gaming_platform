import re

from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    """Requires at least one uppercase letter, one lowercase letter, one digit,
    and one special character, on top of Django's built-in validators
    (length, common-password, numeric-only, user-attribute-similarity)."""

    def validate(self, password, user=None):
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', password):
            errors.append('Password must contain at least one lowercase letter.')
        if not re.search(r'[0-9]', password):
            errors.append('Password must contain at least one digit.')
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append('Password must contain at least one special character.')
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            'Your password must contain at least one uppercase letter, one lowercase '
            'letter, one digit, and one special character.'
        )
