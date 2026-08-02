import re

from django.core.exceptions import ValidationError

NAME_PATTERN = re.compile(r"^[A-Za-z]+(?:[ '-][A-Za-z]+)*$")

# Loose phone-number shape — digits, spaces, hyphens, parens, an optional
# leading "+", with at least 7 actual digits. Deliberately not locked to one
# country's format: organizers/players aren't necessarily all Pakistani, so
# this only needs to catch clearly-wrong values like "abc" or "!!!", not
# enforce a specific national format.
PHONE_PATTERN = re.compile(r'^\+?[\d\s()-]+$')

# Pakistani CNIC: 5 digits - 7 digits - 1 digit, e.g. 42101-1234567-1.
CNIC_PATTERN = re.compile(r'^\d{5}-\d{7}-\d$')

# Pakistani mobile number (with optional +92/0 country prefix and optional
# separators) — used for JazzCash specifically, since JazzCash is a Pakistani
# mobile wallet tied 1:1 to a Pakistani mobile number, unlike a general
# contact phone field which may legitimately be international.
PK_MOBILE_PATTERN = re.compile(r'^(?:\+92|0)3\d{9}$')


def validate_phone_number(value):
    value = (value or '').strip()
    if not value:
        return
    digit_count = sum(c.isdigit() for c in value)
    if digit_count < 7 or not PHONE_PATTERN.match(value):
        raise ValidationError('Enter a valid phone number.')


def validate_cnic_number(value):
    value = (value or '').strip()
    if not value:
        return
    if not CNIC_PATTERN.match(value):
        raise ValidationError('Enter a valid CNIC number in the format 12345-1234567-1.')


def validate_pk_mobile_number(value):
    value = (value or '').strip()
    if not value:
        return
    cleaned = re.sub(r'[\s-]', '', value)
    if not PK_MOBILE_PATTERN.match(cleaned):
        raise ValidationError('Enter a valid Pakistani mobile number, e.g. 03001234567.')


def validate_bank_account_number(value):
    value = (value or '').strip()
    if not value:
        return
    cleaned = value.replace(' ', '').replace('-', '')
    if not (5 <= len(cleaned) <= 34) or not cleaned.isalnum():
        raise ValidationError('Enter a valid bank account number.')

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB — CNIC scans/PDFs never legitimately need more

# Sniffed from the first few bytes of the file itself, not the client-supplied
# filename or Content-Type header (either of which is trivial to spoof).
# SVG is deliberately excluded even though browsers treat it as an image type:
# an <iframe src="...svg"> — exactly how the admin panel previews these
# documents — executes any <script> the SVG contains.
_DOCUMENT_MAGIC_BYTES = (
    b'\xff\xd8\xff',              # JPEG
    b'\x89PNG\r\n\x1a\n',         # PNG
    b'%PDF-',                     # PDF
)


def validate_document_file(file):
    """Restrict an uploaded document (CNIC scan, compliance certificate, payment
    proof) to genuine JPEG/PNG/PDF content and a sane size. Used on every
    FileField that isn't Django's own ImageField (which already runs this kind
    of check via Pillow) — cover_image and game logos are ImageFields and don't
    need this."""
    if file.size > MAX_DOCUMENT_SIZE:
        raise ValidationError(f'File must be smaller than {MAX_DOCUMENT_SIZE // (1024 * 1024)}MB.')

    file.seek(0)
    header = file.read(8)
    file.seek(0)

    if not any(header.startswith(magic) for magic in _DOCUMENT_MAGIC_BYTES):
        raise ValidationError('Only JPEG, PNG, or PDF files are allowed.')


def clean_person_name(value, field_label='This field'):
    """Trim and enforce 2-50 characters of letters, spaces, hyphens, and apostrophes
    only (no leading/trailing/consecutive separators) — used for first/last name
    fields wherever a user can set their own name."""
    value = (value or '').strip()
    if not (2 <= len(value) <= 50):
        raise ValidationError(f'{field_label} must be between 2 and 50 characters.')
    if not NAME_PATTERN.match(value):
        raise ValidationError(f'{field_label} can only contain letters, spaces, hyphens, and apostrophes.')
    return value


class MaximumLengthValidator:
    """Companion to Django's built-in MinimumLengthValidator — caps password length
    so an extremely long input can't be used to burn CPU in the bcrypt hashing step."""

    def __init__(self, max_length=128):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(f'This password must be at most {self.max_length} characters.')

    def get_help_text(self):
        return f'Your password must be at most {self.max_length} characters.'


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
