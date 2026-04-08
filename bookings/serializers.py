from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from .models import Booking, BookingBid


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for booking CRUD with business validations."""

    class Meta:
        model = Booking
        fields = [
            "id",
            "customer",
            "photographer",
            "title",
            "category",
            "shoot_date",
            "deadline_date",
            "location",
            "environment",
            "requires_makeup",
            "budget_min",
            "budget_max",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "customer", "status", "created_at", "updated_at"]

    def validate(self, attrs):
        """Validate shoot date and budget range."""
        shoot_date = attrs.get("shoot_date")
        budget_min = attrs.get("budget_min")
        budget_max = attrs.get("budget_max")

        if shoot_date and shoot_date <= timezone.localdate():
            raise serializers.ValidationError(
                {"shoot_date": "Ngay chup phai lon hon ngay hien tai."}
            )

        if (
            budget_min is not None
            and budget_max is not None
            and budget_max < budget_min
        ):
            raise serializers.ValidationError(
                {"budget_max": "budget_max phai lon hon hoac bang budget_min."}
            )

        return attrs


class BookingBidSerializer(serializers.ModelSerializer):
    """Serializer for bid create/list with anti-duplicate checks."""

    class Meta:
        model = BookingBid
        fields = [
            "id",
            "booking",
            "photographer",
            "proposed_price",
            "cover_letter",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "photographer", "status", "created_at"]

    def validate(self, attrs):
        """Validate that photographer cannot bid own booking or bid twice."""
        request = self.context.get("request")
        booking = attrs.get("booking")

        if not request or request.user.is_anonymous:
            raise serializers.ValidationError("Yeu cau khong hop le.")

        if booking.customer_id == request.user.id:
            raise serializers.ValidationError(
                {"booking": "Khong the dau thau booking cua chinh minh."}
            )

        if booking.status != Booking.Status.OPEN:
            raise serializers.ValidationError(
                {"booking": "Chi co the dau thau booking dang OPEN."}
            )

        if BookingBid.objects.filter(
            booking=booking,
            photographer=request.user,
        ).exists():
            raise serializers.ValidationError(
                {"booking": "Ban da gui bao gia cho booking nay."}
            )

        return attrs

    def create(self, validated_data):
        """Create bid and convert DB unique conflict into serializer error."""
        try:
            return super().create(validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"booking": "Ban da gui bao gia cho booking nay."}
            ) from exc


class AcceptBidSerializer(serializers.Serializer):
    """Payload serializer for booking bid acceptance action."""

    bid_id = serializers.UUIDField()
