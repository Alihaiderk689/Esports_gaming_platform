from rest_framework.throttling import SimpleRateThrottle


class PerFieldRateThrottle(SimpleRateThrottle):
    """Throttles by a value pulled from the request body (e.g. `email`)
    instead of by client IP. Meant to be layered alongside the existing
    IP-scoped ScopedRateThrottle, not replace it: an IP-based limit alone
    lets an attacker distribute login/reset attempts against one account
    across many IPs and stay under the radar. Subclasses only need to set
    `scope` (must exist in DEFAULT_THROTTLE_RATES).

    A request with no value in `field` (e.g. malformed body) is allowed
    through here — the view's own serializer validation rejects it before
    any password/email logic runs, and there is nothing meaningful to key a
    per-account limit on."""

    field = 'email'

    def get_cache_key(self, request, view):
        value = request.data.get(self.field)
        if not value:
            return None
        ident = str(value).strip().lower()
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginEmailRateThrottle(PerFieldRateThrottle):
    scope = 'login_email'


class EmailActionEmailRateThrottle(PerFieldRateThrottle):
    scope = 'email_action_email'
