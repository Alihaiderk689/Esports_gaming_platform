from django.conf import settings
from django.core.checks import Warning, register


@register()
def production_monitoring_check(app_configs, **kwargs):
    """Advisory only — neither REDIS_URL nor SENTRY_DSN is required for the
    app to function, so this warns rather than blocking startup the way the
    EMAIL_BACKEND check in settings.py does for a genuinely broken config.
    Runs on every `manage.py check`/`test`/`migrate` — including on every
    deploy, since backend/entrypoint.sh runs `migrate --noinput` before
    starting gunicorn, and `migrate` runs system checks by default. That
    makes this visible in Render's deploy logs without needing anyone to
    remember to run `manage.py check --deploy` by hand."""
    if settings.ENVIRONMENT != 'production':
        return []

    warnings = []
    if not settings.REDIS_URL:
        warnings.append(Warning(
            'REDIS_URL is not set in production.',
            hint=(
                'DRF throttling falls back to per-process LocMemCache — behind more than one '
                'gunicorn worker/instance, every configured rate limit is effectively '
                '(configured rate) x (worker/instance count), not the configured rate. '
                'See docs/SECURITY_CHECKLIST.md#authentication.'
            ),
            id='core.W001',
        ))
    if not settings.SENTRY_DSN:
        warnings.append(Warning(
            'SENTRY_DSN is not set in production.',
            hint=(
                'Optional, but without it, unhandled errors and the security events logged via '
                'core.security_events are never forwarded anywhere for alerting — they only '
                'reach Render\'s console logs. See docs/SECURITY_CHECKLIST.md#security-monitoring.'
            ),
            id='core.W002',
        ))
    return warnings
