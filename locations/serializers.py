from rest_framework import serializers

from .models import Location


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "city_province", "district"]


class PhotographerLocationSyncSerializer(serializers.Serializer):
    location_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )

    def validate_location_ids(self, value):
        existing_ids = set(
            Location.objects.filter(id__in=value).values_list("id", flat=True)
        )
        missing_ids = sorted(set(value) - existing_ids)
        if missing_ids:
            raise serializers.ValidationError(
                f"Cac location sau khong ton tai: {missing_ids}"
            )
        return value
