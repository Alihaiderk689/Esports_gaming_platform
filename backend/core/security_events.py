import logging

security_logger = logging.getLogger('security')

# Structural backstop for the "never log a secret" rule below — a call site
# that does `log_security_event('x', request=request, **request.data)` (or
# names a field 'reset_token'/'refresh'/etc.) fails loudly instead of
# quietly writing a credential to permanent log storage. Matched as a
# substring against the lowercased field name, not an exact list, since a
# new call site might reasonably call something `google_id_token` or
# `new_password` rather than exactly `token`/`password`.
_FORBIDDEN_FIELD_SUBSTRINGS = ('password', 'token', 'refresh', 'secret', 'authorization', 'cookie')


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def log_security_event(event, request=None, **fields):
    """Structured, secret-free logging for events worth being able to notice
    and alert on — failed logins, password-reset/verification-email abuse,
    admin actions, OAuth failures, repeated authorization failures — as
    opposed to core.audit.log_action's AuditLog, which is a queryable,
    permanent, per-object accountability trail. This is a log line: cheap,
    unstructured-storage, meant for a log aggregator/Sentry/alerting to
    watch, not for a "who did what to this object" API response.

    NEVER pass a password, JWT, refresh token, OAuth id_token, reset/
    verification token, or raw request body into `fields` — same rule as
    log_action's metadata kwarg, for the same reason: this is permanent
    storage outside the code's control once it leaves the process. This is
    enforced, not just documented — see _FORBIDDEN_FIELD_SUBSTRINGS above;
    a field name matching one of those raises rather than logging.

    Only `request.META`'s IP/user-agent and `request.path` are read from the
    request automatically — never `request.data`/`request.body`, and never
    the `Authorization`/`Cookie` headers. Don't pass those in via `fields`
    either.
    """
    for key in fields:
        lowered = key.lower()
        if any(bad in lowered for bad in _FORBIDDEN_FIELD_SUBSTRINGS):
            raise ValueError(
                f'log_security_event: refusing to log field {key!r} for event {event!r} — its name suggests it '
                'may contain a secret. Never pass a password, token, or refresh token into a security event.'
            )
    payload = {'event': event}
    if request is not None:
        payload['ip'] = _client_ip(request)
        payload['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:256]
        payload['path'] = request.path
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            payload['user_id'] = user.pk
    payload.update(fields)
    security_logger.info(payload)
