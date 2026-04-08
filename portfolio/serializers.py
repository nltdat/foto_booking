from django.conf import settings
from rest_framework import serializers

from .models import Portfolio


def _to_public_media_url(url):
    if not url:
        return None

    internal = settings.AWS_S3_ENDPOINT_URL.rstrip("/")
    public = settings.AWS_S3_PUBLIC_ENDPOINT_URL.rstrip("/")

    if url.startswith(internal):
        return f"{public}{url[len(internal):]}"
    return url


class PortfolioSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True, required=True)
    image_url = serializers.SerializerMethodField(read_only=True)
    photographer_id = serializers.IntegerField(source="photographer.id", read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            "id",
            "photographer_id",
            "image",
            "image_url",
            "category",
            "created_at",
        ]
        read_only_fields = ["id", "photographer_id", "image_url", "created_at"]

    @staticmethod
    def get_image_url(obj):
        if not obj.image:
            return None
        return _to_public_media_url(obj.image.url)
