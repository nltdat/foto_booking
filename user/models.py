from django.contrib.auth.models import AbstractUser
from django.db import models


def user_avatar_upload_path(instance, filename):
    return f"users/{instance.id}/avatar/{filename}"


def user_cover_image_upload_path(instance, filename):
    return f"users/{instance.id}/cover/{filename}"


class User(AbstractUser):
    class Roles(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        PHOTOGRAPHER = "PHOTOGRAPHER", "Photographer"
        ADMIN = "ADMIN", "Admin"

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.CUSTOMER,
    )
    avatar = models.URLField(blank=True, default="")
    cover_image = models.URLField(blank=True, default="")

    def __str__(self):
        return f"{self.username} ({self.role})"


class PhotographerProfile(models.Model):
    class Genders(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="photographer_profile",
    )
    bio = models.TextField(blank=True)
    specialties = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    experience_years = models.PositiveSmallIntegerField(default=0)
    gender = models.CharField(
        max_length=20,
        choices=Genders.choices,
        blank=True,
        default="",
    )
    languages = models.JSONField(default=list, blank=True)
    working_models = models.JSONField(default=list, blank=True)
    working_packages = models.JSONField(default=list, blank=True)
    rating_avg = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
    )
    total_reviews = models.PositiveIntegerField(default=0)
    active_locations = models.ManyToManyField(
        "locations.Location",
        related_name="locations",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PhotographerProfile<{self.user.username}>"


class PhotographerFavorite(models.Model):
    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="photographer_favorites",
    )
    photographer = models.ForeignKey(
        PhotographerProfile,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["photographer", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "photographer"],
                name="unique_customer_photographer_favorite",
            ),
        ]

    def __str__(self):
        return f"PhotographerFavorite<{self.customer_id}:{self.photographer_id}>"
