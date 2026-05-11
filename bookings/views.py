from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from fotonow.pagination import DefaultPageNumberPagination
from user.models import User

from .models import Booking, BookingBid
from .permissions import IsBookingOwner, IsCustomer, IsPhotographer
from .serializers import AcceptBidSerializer, BookingBidSerializer, BookingSerializer


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for booking management and bid acceptance workflow."""

    serializer_class = BookingSerializer
    pagination_class = DefaultPageNumberPagination
    queryset = Booking.objects.select_related(
        "customer",
        "photographer",
        "location",
    )

    def get_permissions(self):
        """Role-based permissions per action."""
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]

        if self.action == "create":
            return [permissions.IsAuthenticated(), IsCustomer()]

        if self.action == "accept_bid":
            return [permissions.IsAuthenticated(), IsBookingOwner()]

        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """Photographers see OPEN market; customers see own bookings."""
        user = self.request.user
        queryset = self.queryset

        if self.action == "accept_bid":
            return queryset

        if not user.is_authenticated:
            queryset = queryset.filter(status=Booking.Status.OPEN)
            location = self.request.query_params.get("location")
            category = self.request.query_params.get("category")
            if location:
                queryset = queryset.filter(location_id=location)
            if category:
                queryset = queryset.filter(category=category)
            return queryset

        if user.role == User.Roles.PHOTOGRAPHER:
            queryset = queryset.filter(status=Booking.Status.OPEN)
            location = self.request.query_params.get("location")
            category = self.request.query_params.get("category")
            if location:
                queryset = queryset.filter(location_id=location)
            if category:
                queryset = queryset.filter(category=category)
            return queryset

        if user.role == User.Roles.CUSTOMER:
            return queryset.filter(customer=user)

        return queryset

    @extend_schema(
        summary="Danh sach booking",
        description=(
            "Photographer chi thay booking OPEN trong cho viec lam. "
            "Ho tro filter theo location va category."
        ),
        parameters=[
            OpenApiParameter(
                name="location",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Loc theo location id.",
            ),
            OpenApiParameter(
                name="category",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Loc theo category.",
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """List bookings based on role-scoped queryset."""
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Set booking owner as authenticated customer."""
        serializer.save(customer=self.request.user)

    @extend_schema(
        summary="Chap nhan bao gia",
        description=(
            "Nhan bid_id trong request body, set bid do thanh ACCEPTED, "
            "set booking thanh MATCHED, va set cac bid con lai thanh REJECTED."
        ),
        request=AcceptBidSerializer,
        responses={200: BookingSerializer},
    )
    @action(detail=True, methods=["post"])
    def accept_bid(self, request, pk=None):
        """Accept one bid for this booking with atomic transaction."""
        booking = self.get_object()
        self.check_object_permissions(request, booking)

        bid_id = request.data.get("bid_id")
        if not bid_id:
            return Response(
                {"detail": "bid_id la bat buoc."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)

            if booking.status != Booking.Status.OPEN:
                return Response(
                    {"detail": "Chi co the chap nhan bid khi booking dang OPEN."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                selected_bid = BookingBid.objects.select_for_update().get(
                    id=bid_id,
                    booking=booking,
                )
            except BookingBid.DoesNotExist:
                return Response(
                    {"detail": "Bid khong thuoc booking nay hoac khong ton tai."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            selected_bid.status = BookingBid.Status.ACCEPTED
            selected_bid.save(update_fields=["status"])

            BookingBid.objects.filter(booking=booking).exclude(
                id=selected_bid.id
            ).update(status=BookingBid.Status.REJECTED)

            booking.status = Booking.Status.MATCHED
            if booking.photographer_id is None:
                booking.photographer = selected_bid.photographer
            booking.save(update_fields=["status", "photographer", "updated_at"])

        return Response(
            self.get_serializer(booking).data,
            status=status.HTTP_200_OK,
        )


class BookingBidViewSet(viewsets.ModelViewSet):
    """ViewSet for photographer bidding and owner-facing bid listing."""

    serializer_class = BookingBidSerializer
    pagination_class = DefaultPageNumberPagination
    queryset = BookingBid.objects.select_related(
        "booking",
        "booking__customer",
        "photographer",
    )

    def get_permissions(self):
        """Only photographers can create bids; authenticated users can list/retrieve."""
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsPhotographer()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        """Customers only see bids for their bookings; photographers see own bids."""
        user = self.request.user

        if user.role == User.Roles.CUSTOMER:
            return self.queryset.filter(booking__customer=user)

        if user.role == User.Roles.PHOTOGRAPHER:
            return self.queryset.filter(photographer=user)

        return self.queryset

    def perform_create(self, serializer):
        """Assign authenticated photographer as bid owner."""
        serializer.save(photographer=self.request.user)
