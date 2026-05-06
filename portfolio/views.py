from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from fotonow.pagination import DefaultPageNumberPagination
from user.models import PhotographerProfile, User

from .models import Portfolio
from .serializers import PortfolioSerializer


class IsOwnerOrReadOnly(permissions.BasePermission):
    message = "Ban khong co quyen chinh sua portfolio cua nguoi khac."

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        if not bool(request.user and request.user.is_authenticated):
            return False

        if getattr(view, "action", None) == "create":
            return request.user.role == User.Roles.PHOTOGRAPHER

        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.photographer.user_id == request.user.id


class PortfolioFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        category = request.query_params.get("category")
        photographer_id = request.query_params.get("photographer_id")

        if category:
            queryset = queryset.filter(category=category)
        if photographer_id:
            queryset = queryset.filter(photographer_id=photographer_id)
        return queryset


@extend_schema_view(
    list=extend_schema(
        tags=["Portfolios"],
        summary="Danh sach portfolio",
        parameters=[
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Loc theo category (PERSONAL, COUPLE, EVENT, WEDDING, FAMILY)",
            ),
            OpenApiParameter(
                name="photographer_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Loc theo photographer profile id",
            ),
        ],
    ),
    create=extend_schema(
        tags=["Portfolios"],
        summary="Upload anh portfolio",
        request={"multipart/form-data": PortfolioSerializer},
        responses={201: PortfolioSerializer},
    ),
)
class PortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioSerializer
    pagination_class = DefaultPageNumberPagination
    permission_classes = [IsOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [PortfolioFilterBackend]
    queryset = Portfolio.objects.select_related(
        "photographer",
        "photographer__user",
    ).all()

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_authenticated:
            raise PermissionDenied("Ban can dang nhap de upload portfolio.")
        if user.role != User.Roles.PHOTOGRAPHER:
            raise PermissionDenied(
                "Chi nhiep anh gia moi co the upload portfolio."
            )

        profile, _ = PhotographerProfile.objects.get_or_create(user=user)
        serializer.save(photographer=profile)
