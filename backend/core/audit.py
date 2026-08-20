from django.contrib.contenttypes.models import ContentType

from core.models import AuditLog


def log_action(actor, action, target, reason='', **metadata):
    """Record an AuditLog entry. `actor` may be None (system-initiated action).
    `metadata` is stored as-is in the JSONField — keep values JSON-serializable
    (e.g. isoformat() datetimes, not raw datetime objects)."""
    AuditLog.objects.create(
        actor=actor,
        action=action,
        content_type=ContentType.objects.get_for_model(target),
        object_id=target.pk,
        reason=reason,
        metadata=metadata,
    )
