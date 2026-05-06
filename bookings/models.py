import uuid

from django.conf import settings
from django.db import models


class Booking(models.Model):
    """Customer booking request for public gig or direct photographer booking."""

    class Categories(models.TextChoices):
        PERSONAL = "PERSONAL", "Personal"
        COUPLE = "COUPLE", "Couple"
        EVENT = "EVENT", "Event"
        WEDDING = "WEDDING", "Wedding"
        FAMILY = "FAMILY", "Family"

    class Environments(models.TextChoices):
        INDOOR = "INDOOR", "Indoor"
        OUTDOOR = "OUTDOOR", "Outdoor"
        STUDIO = "STUDIO", "Studio"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        MATCHED = "MATCHED", "Matched"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings_created",
    )
    photographer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="bookings_assigned",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=Categories.choices)
    shoot_date = models.DateField()
    deadline_date = models.DateTimeField()
    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    environment = models.CharField(max_length=20, choices=Environments.choices)
    requires_makeup = models.BooleanField(default=False)
    budget_min = models.DecimalField(max_digits=12, decimal_places=2)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["shoot_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(budget_max__gte=models.F("budget_min")),
                name="booking_budget_max_gte_budget_min",
            ),
        ]

    def __str__(self):
        return f"Booking<{self.id}> {self.title}"


class BookingBid(models.Model):
    """Photographer bid submitted for a booking."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="bids",
    )
    photographer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="booking_bids",
    )
    proposed_price = models.DecimalField(max_digits=12, decimal_places=2)
    cover_letter = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["photographer", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "photographer"],
                name="unique_booking_bid_per_photographer",
            ),
        ]

    def __str__(self):
        return f"BookingBid<{self.id}>"
