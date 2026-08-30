from django.conf import settings

REFRESH_COOKIE_NAME = 'esp_refresh'
# Scoped to the auth namespace only — the browser never attaches this cookie
# to any other API request, limiting what a CSRF-triggered request could
# even reach.
REFRESH_COOKIE_PATH = '/api/auth/'


def set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        REFRESH_COOKIE_NAME, refresh_token,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, samesite=settings.AUTH_COOKIE_SAMESITE)
