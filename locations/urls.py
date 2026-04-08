from django.urls import path

from .views import LocationListAPIView, PhotographerLocationSyncAPIView

urlpatterns = [
    path("locations/", LocationListAPIView.as_view(), name="location-list"),
    path(
        "photographers/me/locations/",
        PhotographerLocationSyncAPIView.as_view(),
        name="photographers-me-locations",
    ),
]
