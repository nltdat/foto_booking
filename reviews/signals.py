from django.db.models import Avg, Count
from django.db.models.signals import post_save
from django.dispatch import receiver

from user.models import PhotographerProfile

from .models import Review


@receiver(post_save, sender=Review)
def update_photographer_rating_on_review_save(sender, instance, created, **kwargs):
    """Recalculate photographer rating aggregates after creating a review."""

    if not created:
        return

    stats = Review.objects.filter(reviewee_id=instance.reviewee_id).aggregate(
        rating_avg=Avg("rating"),
        total_reviews=Count("id"),
    )

    profile, _ = PhotographerProfile.objects.get_or_create(user_id=instance.reviewee_id)
    profile.rating_avg = round(float(stats["rating_avg"] or 0), 2)
    profile.total_reviews = stats["total_reviews"] or 0
    profile.save(update_fields=["rating_avg", "total_reviews", "updated_at"])
