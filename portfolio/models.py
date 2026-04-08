import uuid

from django.db import models


def portfolio_image_upload_path(instance, filename):
    return f"portfolios/{instance.photographer_id}/{filename}"


class Portfolio(models.Model):
    class Categories(models.TextChoices):
        PERSONAL = "PERSONAL", "Personal"
        COUPLE = "COUPLE", "Couple"
        EVENT = "EVENT", "Event"
        WEDDING = "WEDDING", "Wedding"
        FAMILY = "FAMILY", "Family"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photographer = models.ForeignKey(
        "user.PhotographerProfile",
        on_delete=models.CASCADE,
        related_name="portfolios",
    )
    image = models.ImageField(upload_to=portfolio_image_upload_path)
    category = models.CharField(max_length=20, choices=Categories.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["photographer", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self):
        return f"Portfolio<{self.id}>"
