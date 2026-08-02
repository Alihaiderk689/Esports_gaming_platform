"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.static import serve

from core.views import secure_media_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('secure-media/', secure_media_view),
    path('api/', include('core.urls')),
    path('api/', include('games.urls')),
    path('api/', include('organizer.urls')),
    path('api/', include('tourny_regist.urls')),
    path('api/', include('brackets.urls')),
    path('api/', include('partners.urls')),
    path('api/', include('dashboard.urls')),
    path('api/', include('rag_chat.urls')),
]

if settings.DEBUG:
    # Only genuinely public uploads (game logos, tournament cover images — both
    # meant to be visible to logged-out visitors browsing the site) are served
    # from here and stay on local disk. Sensitive uploads (CNIC scans, payment
    # proofs, compliance documents) live in Cloudinary via CloudinarySignedStorage
    # instead — see core/storage.py and secure_media_view above — precisely so
    # they're NOT reachable through this catch-all just by guessing a path.
    #
    # Exempt from clickjacking protection (X_FRAME_OPTIONS='DENY' above) so cover
    # images can be previewed in an <iframe> the same way secure_media_view's docs
    # are. never_cache prevents browsers from reusing a stale cached copy of a
    # response that was served (and blocked) before this exemption was in place,
    # since django.views.static.serve doesn't send Cache-Control and browsers
    # heuristically cache on Last-Modified alone.
    public_media_serve = never_cache(xframe_options_exempt(serve))
    media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        path(f'{media_prefix}games/logos/<path:path>', public_media_serve, {'document_root': settings.MEDIA_ROOT / 'games' / 'logos'}),
        path(f'{media_prefix}tournaments/covers/<path:path>', public_media_serve, {'document_root': settings.MEDIA_ROOT / 'tournaments' / 'covers'}),
    ]
