from bookings.models import Booking
from rest_framework import permissions


class IsBookingParticipant(permissions.BasePermission):
    """Only booking customer can create a review for that booking."""

    message = "Ban khong co quyen danh gia booking nay."

    def has_permission(self, request, view):
        if request.method != "POST":
            return True

        booking_id = request.data.get("booking")
        if not booking_id or not request.user or not request.user.is_authenticated:
            return False

        try:
            booking = Booking.objects.only("id", "customer_id").get(id=booking_id)
        except Booking.DoesNotExist:
            return False

        return booking.customer_id == request.user.id

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.reviewer_id == request.user.id
