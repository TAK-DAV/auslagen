from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.views.static import serve

from tak.views import home

urlpatterns = [
    path("", home, name="home"),
    path("einreichen/", include("portal.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Receipts and donation PDFs: only for signed-in users (not public CDN).
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            login_required(serve),
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
