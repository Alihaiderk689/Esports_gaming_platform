from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from rest_framework.views import exception_handler as drf_default_exception_handler

from core.security_events import log_security_event

# The exception types worth watching in aggregate: a spike in any of these
# across many requests is what "100 failed logins" / "repeated authorization
# failures" actually looks like from a log-monitoring standpoint. Ordinary
# validation errors (400s from bad form input) are deliberately excluded —
# noisy, not security-relevant on their own.
_SECURITY_RELEVANT_EXCEPTIONS = (Throttled, NotAuthenticated, AuthenticationFailed, PermissionDenied)


def security_aware_exception_handler(exc, context):
    """DRF's REST_FRAMEWORK['EXCEPTION_HANDLER'] — wraps the default handler
    so every 401/403/429 across the entire API is logged as a structured
    security event centrally, rather than requiring every view to remember
    to log its own denial. See core.security_events.log_security_event."""
    response = drf_default_exception_handler(exc, context)
    if isinstance(exc, _SECURITY_RELEVANT_EXCEPTIONS):
        request = context.get('request')
        log_security_event(
            f'http.{type(exc).__name__.lower()}',
            request=request,
            status_code=response.status_code if response is not None else None,
        )
    return response
