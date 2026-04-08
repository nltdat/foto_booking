from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from user.models import PhotographerProfile, User

from .models import Location
from .serializers import LocationSerializer, PhotographerLocationSyncSerializer


class LocationModelTest(TestCase):
    def test_str_representation(self):
        location = Location(city_province="Ha Noi", district="Hoan Kiem")
        self.assertEqual(str(location), "Ha Noi - Hoan Kiem")

    def test_unique_constraint_city_district(self):
        Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")

    def test_ordering_by_city_then_district(self):
        Location.objects.create(city_province="Ho Chi Minh", district="Q1")
        Location.objects.create(city_province="Ha Noi", district="Dong Da")
        Location.objects.create(city_province="Ha Noi", district="Ba Dinh")
        locations = list(Location.objects.all())
        self.assertEqual(locations[0].city_province, "Ha Noi")
        self.assertEqual(locations[0].district, "Ba Dinh")
        self.assertEqual(locations[1].district, "Dong Da")
        self.assertEqual(locations[2].city_province, "Ho Chi Minh")

    def test_create_location(self):
        loc = Location.objects.create(city_province="Da Nang", district="Hai Chau")
        self.assertEqual(loc.city_province, "Da Nang")
        self.assertEqual(loc.district, "Hai Chau")
        self.assertIsNotNone(loc.pk)


class LocationSerializerTest(TestCase):
    def test_serializes_location_fields(self):
        loc = Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        data = LocationSerializer(loc).data
        self.assertEqual(data["city_province"], "Ha Noi")
        self.assertEqual(data["district"], "Hoan Kiem")
        self.assertIn("id", data)

    def test_all_fields_present(self):
        loc = Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        data = LocationSerializer(loc).data
        self.assertEqual(set(data.keys()), {"id", "city_province", "district"})


class PhotographerLocationSyncSerializerTest(TestCase):
    def setUp(self):
        self.loc1 = Location.objects.create(city_province="Ha Noi", district="Ba Dinh")
        self.loc2 = Location.objects.create(city_province="Ha Noi", district="Dong Da")

    def test_valid_location_ids(self):
        serializer = PhotographerLocationSyncSerializer(
            data={"location_ids": [self.loc1.pk, self.loc2.pk]}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_empty_location_ids_allowed(self):
        serializer = PhotographerLocationSyncSerializer(data={"location_ids": []})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_missing_location_id_raises_error(self):
        serializer = PhotographerLocationSyncSerializer(
            data={"location_ids": [self.loc1.pk, 99999]}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("location_ids", serializer.errors)
        error_str = str(serializer.errors["location_ids"])
        self.assertIn("99999", error_str)

    def test_all_missing_ids_reported(self):
        serializer = PhotographerLocationSyncSerializer(
            data={"location_ids": [88888, 99999]}
        )
        self.assertFalse(serializer.is_valid())
        error_str = str(serializer.errors["location_ids"])
        self.assertIn("88888", error_str)
        self.assertIn("99999", error_str)

    def test_negative_id_fails_validation(self):
        serializer = PhotographerLocationSyncSerializer(
            data={"location_ids": [-1]}
        )
        self.assertFalse(serializer.is_valid())

    def test_location_ids_field_required(self):
        serializer = PhotographerLocationSyncSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("location_ids", serializer.errors)


class LocationListAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("location-list")

    def test_public_access_no_auth_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_all_locations(self):
        Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        Location.objects.create(city_province="Da Nang", district="Hai Chau")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_returns_empty_when_no_locations(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_results_ordered_by_city_then_district(self):
        Location.objects.create(city_province="Ho Chi Minh", district="Q1")
        Location.objects.create(city_province="Ha Noi", district="Dong Da")
        Location.objects.create(city_province="Ha Noi", district="Ba Dinh")
        response = self.client.get(self.url)
        results = response.data
        self.assertEqual(results[0]["city_province"], "Ha Noi")
        self.assertEqual(results[0]["district"], "Ba Dinh")
        self.assertEqual(results[1]["district"], "Dong Da")

    def test_location_response_has_correct_fields(self):
        Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        response = self.client.get(self.url)
        item = response.data[0]
        self.assertIn("id", item)
        self.assertIn("city_province", item)
        self.assertIn("district", item)


class PhotographerLocationSyncAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url_get = reverse("photographers-me-locations")
        self.url_put = reverse("photographers-me-locations")

        self.photographer_user = User.objects.create_user(
            username="photographer1",
            email="photo@test.com",
            password="pass123",
            role=User.Roles.PHOTOGRAPHER,
        )
        self.customer_user = User.objects.create_user(
            username="customer1",
            email="customer@test.com",
            password="pass123",
            role=User.Roles.CUSTOMER,
        )
        self.loc1 = Location.objects.create(city_province="Ha Noi", district="Ba Dinh")
        self.loc2 = Location.objects.create(city_province="Ha Noi", district="Dong Da")

    def test_get_requires_authentication(self):
        response = self.client.get(self.url_get)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_requires_photographer_role(self):
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get(self.url_get)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photographer_get_empty_locations(self):
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.get(self.url_get)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_photographer_get_locations_after_sync(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.photographer_user)
        profile.active_locations.set([self.loc1, self.loc2])
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.get(self.url_get)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_put_requires_authentication(self):
        response = self.client.put(
            self.url_put, {"location_ids": [self.loc1.pk]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_requires_photographer_role(self):
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.put(
            self.url_put, {"location_ids": [self.loc1.pk]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photographer_sync_locations(self):
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.put(
            self.url_put,
            {"location_ids": [self.loc1.pk, self.loc2.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_photographer_sync_empty_clears_locations(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.photographer_user)
        profile.active_locations.set([self.loc1, self.loc2])
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.put(
            self.url_put, {"location_ids": []}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
        profile.refresh_from_db()
        self.assertEqual(profile.active_locations.count(), 0)

    def test_sync_with_nonexistent_location_id_returns_400(self):
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.put(
            self.url_put, {"location_ids": [99999]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sync_replaces_existing_locations(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.photographer_user)
        profile.active_locations.set([self.loc1])
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.put(
            self.url_put, {"location_ids": [self.loc2.pk]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.loc2.pk)

    def test_sync_results_ordered_by_city_then_district(self):
        loc3 = Location.objects.create(city_province="Ha Noi", district="Cau Giay")
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.put(
            self.url_put,
            {"location_ids": [self.loc2.pk, self.loc1.pk, loc3.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Results should be ordered: Ba Dinh, Cau Giay, Dong Da
        districts = [item["district"] for item in response.data]
        self.assertEqual(districts, sorted(districts))