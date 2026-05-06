from django.db import models


class Location(models.Model):
    city_province = models.CharField(max_length=120)
    district = models.CharField(max_length=120)

    class Meta:
        ordering = ["city_province", "district"]
        constraints = [
            models.UniqueConstraint(
                fields=["city_province", "district"],
                name="unique_city_province_district",
            )
        ]

    def __str__(self):
        return f"{self.city_province} - {self.district}"
