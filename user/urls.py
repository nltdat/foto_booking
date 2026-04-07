from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    HealthCheckAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    PhotographerMeProfileAPIView,
    RegisterAPIView,
)

urlpatterns = [
    path("health/", HealthCheckAPIView.as_view(), name="health-check"),
    path("auth/register/", RegisterAPIView.as_view(), name="auth-register"),
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("users/me/", MeAPIView.as_view(), name="users-me"),
    path(
        "photographers/me/profile/",
        PhotographerMeProfileAPIView.as_view(),
        name="photographers-me-profile",
    ),
]
