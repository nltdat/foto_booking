from django.contrib.auth.models import AbstractUser
from django.db import models


def user_avatar_upload_path(instance, filename):
    return f"users/{instance.id}/avatar/{filename}"


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

    def __str__(self):
        return f"{self.username} ({self.role})"


class PhotographerProfile(models.Model):
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
