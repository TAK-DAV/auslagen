from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from django.urls import include

from tak.views import home

urlpatterns = [
    path("", home, name="home"),
    path("einreichen/", include("portal.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
