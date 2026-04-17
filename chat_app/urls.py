"""
URL configuration for chat_app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from django.conf.urls.static import static
from django.contrib import admin
from django.templatetags.static import static as static_tag
from django.urls import include, path
from django.views.generic.base import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("favicon.ico", RedirectView.as_view(url=static_tag("chat.png"))),
        path(
            "swagger", RedirectView.as_view(pattern_name="api_swagger", permanent=False)
        ),
        path(
            "swagger/",
            RedirectView.as_view(pattern_name="api_swagger", permanent=False),
        ),
        path("api/schema/", SpectacularAPIView.as_view(), name="api_schema"),
        path(
            "api/docs/swagger/",
            SpectacularSwaggerView.as_view(url_name="api_schema"),
            name="api_swagger",
        ),
        path(
            "api/docs/redoc/",
            SpectacularRedocView.as_view(url_name="api_schema"),
            name="api_redoc",
        ),
        path("api/v1/", include("chat.api.urls")),
        path("", include("chat.urls")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
)
