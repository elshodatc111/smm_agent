from django.urls import include, path

handler400 = "apps.web.spa.error_400"
handler403 = "apps.web.spa.error_403"
handler404 = "apps.web.spa.error_404"
handler500 = "apps.web.spa.error_500"

urlpatterns = [
    path("api/v1/", include("apps.web.api_urls")),
    path("", include("apps.web.urls")),
]
