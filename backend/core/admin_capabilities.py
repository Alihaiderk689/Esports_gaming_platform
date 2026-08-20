"""Extension point for a future granular admin permission tier.

Today every `Admin*View` across `core`, `tourny_regist`, `organizer`,
`dashboard`, and `rag_chat` is gated by `permissions.IsAdminUser` — any
`is_staff` account can use every admin endpoint (see SECURITY.md#authorization
for the tradeoff and why it hasn't been split up yet: it's a real, sizeable
feature touching every admin view, not something to bolt on as a side effect
of a security pass).

This module exists so that *when* that becomes worth doing, it's a change in
one place per view (swap `permissions.IsAdminUser` for
`HasAdminCapability('manage_tournaments')`, say) rather than a redesign.
`HasAdminCapability` behaves identically to `IsAdminUser` right now — every
`is_staff` account passes every capability check, because there is no
capability data on `User` yet — so adopting it early on a new admin view
costs nothing today and pays off the moment granular roles actually land.

Capability names are deliberately not yet backed by anything (no field on
`User`, no migration) — the list below is a starting inventory of what a real
rollout would likely need, not a contract anything currently checks against.
"""

from rest_framework import permissions

# What a real rollout would likely split IsAdminUser into. Not read by
# anything yet — see the module docstring.
ADMIN_CAPABILITIES = (
    'manage_users',
    'manage_tournaments',
    'manage_organizers',
    'manage_disputes',
    'manage_rulebooks',
    'manage_reviews',
)


class HasAdminCapability(permissions.BasePermission):
    """Drop-in replacement for `permissions.IsAdminUser` on a new admin view.
    Behaves identically today (`is_staff` is sufficient) — the `capability`
    argument is accepted now so call sites don't need to change again later,
    but nothing currently narrows access based on it."""

    def __init__(self, capability):
        assert capability in ADMIN_CAPABILITIES, f'Unknown admin capability: {capability!r}'
        self.capability = capability

    def __call__(self):
        # DRF instantiates each entry in `permission_classes` with no args
        # (`cls()`), so this class is used as `permission_classes = [HasAdminCapability('manage_disputes')]`
        # instead — the instance itself is already callable-as-permission,
        # this just satisfies DRF's "permission_classes holds classes, not
        # instances" expectation without needing a factory function.
        return self

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)
