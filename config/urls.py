from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("apps.web.api_urls")),
    path("", include("apps.web.urls")),
]

handler403 = "apps.web.views_core.permission_denied"
