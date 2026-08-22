import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_SEND_URL = 'https://api.brevo.com/v3/smtp/email'
# Brevo has historically been reliable well within this; bounded mainly so a
# Brevo outage can't hang the request that triggered the email (announcement/
# reschedule emails send synchronously, in a loop, inside the view that
# triggered them — same constraint the SMTP backend it replaces had).
REQUEST_TIMEOUT = 10


def _address_dict(address):
    """'Name <a@b.com>' -> {'email': 'a@b.com', 'name': 'Name'}; a bare
    'a@b.com' -> {'email': 'a@b.com'} — matches how Django's SMTP backend
    has always accepted either form in from_email/recipient_list."""
    name, email = parseaddr(address)
    return {'email': email, 'name': name} if name else {'email': email}


class BrevoAPIBackend(BaseEmailBackend):
    """Sends mail via Brevo's transactional email API instead of SMTP.
    Replaces django.core.mail.backends.smtp.EmailBackend — every existing
    call site (core/emails.py, tourny_regist/emails.py) just calls Django's
    ordinary send_mail()/EmailMessage.send(), unchanged; only EMAIL_BACKEND
    changes, which is exactly what Django's backend abstraction is for.

    Every current call site sends a plain-text, single-part message (no
    attachments, no HTML alternative) — that's what this backend implements.
    An attachment is not silently dropped: it's logged loudly so a future
    call site that adds one notices immediately instead of wondering why
    recipients never got it.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'BREVO_API_KEY', '')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ValueError('BREVO_API_KEY is not set — cannot send email via Brevo.')

        sent_count = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent_count += 1
            except Exception:
                logger.exception('Failed to send email via Brevo (subject=%r)', message.subject)
                if not self.fail_silently:
                    raise
        return sent_count

    def _send_one(self, message):
        if message.attachments:
            logger.warning(
                'Email (subject=%r) has %d attachment(s) — BrevoAPIBackend does not send '
                'attachments, they will be silently omitted.',
                message.subject, len(message.attachments),
            )

        payload = {
            'sender': _address_dict(message.from_email),
            'to': [_address_dict(addr) for addr in message.to],
            'subject': message.subject,
            'textContent': message.body,
        }
        if message.cc:
            payload['cc'] = [_address_dict(addr) for addr in message.cc]
        if message.bcc:
            payload['bcc'] = [_address_dict(addr) for addr in message.bcc]
        if message.reply_to:
            payload['replyTo'] = _address_dict(message.reply_to[0])

        try:
            response = requests.post(
                BREVO_SEND_URL,
                json=payload,
                headers={
                    'accept': 'application/json',
                    'content-type': 'application/json',
                    'api-key': self.api_key,
                },
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            # Split from the non-2xx case below: this is Brevo being
            # unreachable at all (network blip, DNS, timeout) — a different
            # failure mode than Brevo actively rejecting the request, and one
            # a caller diagnosing "why aren't emails sending" needs to be
            # able to tell apart from the other at a glance, not by parsing a
            # generic traceback. Logged before raising so send_messages'
            # per-recipient try/except (the "one bad recipient doesn't break
            # the batch" guarantee) still applies unchanged above this.
            logger.error(
                'Brevo API unreachable sending to %s (subject=%r): %s', message.to, message.subject, exc,
            )
            raise RuntimeError(f'Could not reach the Brevo API sending to {message.to}: {exc}') from exc

        if response.status_code >= 400:
            # The status code + response body are exactly what distinguishes
            # "BREVO_API_KEY is wrong" (401) from "sender not verified in
            # Brevo's dashboard" (400, the specific silent-failure mode
            # docs/SECURITY_CHECKLIST.md warns about) from a transient 5xx —
            # log them as their own clearly-labeled line, not just folded
            # into a stack trace, so that distinction is visible without
            # reproducing the failure separately to find out which one it was.
            logger.error(
                'Brevo API rejected an email to %s (subject=%r): HTTP %s — %s',
                message.to, message.subject, response.status_code, response.text[:500],
            )
            raise RuntimeError(
                f'Brevo API returned {response.status_code} sending to {message.to}: {response.text[:500]}',
            )
