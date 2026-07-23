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

urlpatterns = [
    path('admin/', admin.site.urls),
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
    # Exempt media from clickjacking protection (X_FRAME_OPTIONS='DENY' above) so uploaded
    # documents (e.g. organizer CNIC/company docs) can be previewed in an <iframe> by the admin UI.
    # never_cache prevents browsers from reusing a stale cached copy of a response that was
    # served (and blocked) before this exemption was in place, since django.views.static.serve
    # doesn't send Cache-Control and browsers heuristically cache on Last-Modified alone.
    media_serve = never_cache(xframe_options_exempt(serve))
    urlpatterns += [
        path(
            f'{settings.MEDIA_URL.lstrip("/")}<path:path>',
            media_serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
