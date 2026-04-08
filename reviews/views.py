from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Review
from .permissions import IsBookingParticipant
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    """Create and list reviews for photographers."""

    serializer_class = ReviewSerializer
    queryset = Review.objects.select_related(
        "booking",
        "reviewer",
        "reviewee",
    ).order_by("-created_at")
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsBookingParticipant()]
        return [permissions.AllowAny()]

    @extend_schema(
        tags=["Reviews"],
        summary="Tao danh gia sau buoi chup",
        description=(
            "Chi khach hang cua booking moi duoc tao review. "
            "Booking phai COMPLETED va chua co review."
        ),
        responses={
            201: ReviewSerializer,
            400: OpenApiResponse(
                description="Booking chua COMPLETED hoac da duoc review.",
                examples=[
                    OpenApiExample(
                        "Booking chua hoan thanh",
                        value={"non_field_errors": ["Booking chua o trang thai COMPLETED."]},
                    ),
                    OpenApiExample(
                        "Da ton tai review",
                        value={"non_field_errors": ["Booking nay da duoc danh gia truoc do."]},
                    ),
                ],
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        booking = serializer.validated_data["booking"]
        serializer.save(
            reviewer=self.request.user,
            reviewee=booking.photographer,
        )

    @extend_schema(
        tags=["Reviews"],
        summary="Danh sach review cua nhiep anh gia",
        description="API public de xem review theo photographer_id.",
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"photographer/(?P<photographer_id>[^/.]+)",
        permission_classes=[permissions.AllowAny],
    )
    def photographer(self, request, photographer_id=None):
        queryset = self.filter_queryset(
            self.get_queryset().filter(reviewee_id=photographer_id)
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
