from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


class FotonowSpectacularAPIView(SpectacularAPIView):
    name = "schema"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("user.urls")),
    path("api/", include("locations.urls")),
    path("api/", include("portfolio.urls")),
    path(
        "api/schema/",
        FotonowSpectacularAPIView.as_view(name="schema"),
        name="schema",
    ),
    path(
        "api/schema/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
