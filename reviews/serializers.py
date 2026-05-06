from bookings.models import Booking
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for creating and reading reviews."""

    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = [
            "id",
            "booking",
            "reviewer",
            "reviewee",
            "rating",
            "comment",
            "created_at",
        ]
        read_only_fields = ["id", "reviewer", "reviewee", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_booking(self, obj):
        return str(obj.booking_id)

    def validate(self, attrs):
        request = self.context.get("request")
        booking = attrs.get("booking")

        if request is None or request.user.is_anonymous:
            raise serializers.ValidationError("Ban can dang nhap de tao danh gia.")

        if booking.customer_id != request.user.id:
            raise serializers.ValidationError(
                "Ban khong phai la khach hang cua booking nay."
            )

        if booking.status != Booking.Status.COMPLETED:
            raise serializers.ValidationError(
                "Booking chua o trang thai COMPLETED."
            )

        if booking.photographer_id is None:
            raise serializers.ValidationError(
                "Booking chua co nhiep anh gia duoc gan."
            )

        if hasattr(booking, "review"):
            raise serializers.ValidationError(
                "Booking nay da duoc danh gia truoc do."
            )

        return attrs
