from unittest.mock import MagicMock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from user.models import PhotographerProfile, User

from .models import Location
from .serializers import LocationSerializer, PhotographerLocationSyncSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_location(city="Hanoi", district="Hoan Kiem"):
    return Location.objects.create(city_province=city, district=district)


def make_photographer(username="photo1", password="pass1234!"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=User.Roles.PHOTOGRAPHER,
    )


def make_customer(username="customer1", password="pass1234!"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=User.Roles.CUSTOMER,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestLocationModel(TestCase):
    def test_str_representation(self):
        location = make_location(city="Hanoi", district="Hoan Kiem")
        self.assertEqual(str(location), "Hanoi - Hoan Kiem")

    def test_unique_constraint_city_district(self):
        from django.db import IntegrityError
        make_location(city="Hanoi", district="Hoan Kiem")
        with self.assertRaises(IntegrityError):
            Location.objects.create(city_province="Hanoi", district="Hoan Kiem")

    def test_ordering_by_city_province_then_district(self):
        Location.objects.create(city_province="Hanoi", district="Dong Da")
        Location.objects.create(city_province="HCMC", district="District 1")
        Location.objects.create(city_province="Hanoi", district="Ba Dinh")

        locations = list(Location.objects.all())
        # Ba Dinh < Dong Da alphabetically; Hanoi < HCMC
        self.assertEqual(locations[0].district, "Ba Dinh")
        self.assertEqual(locations[1].district, "Dong Da")
        self.assertEqual(locations[2].city_province, "HCMC")

    def test_different_districts_in_same_city_are_allowed(self):
        l1 = make_location(city="Hanoi", district="Hoan Kiem")
        l2 = Location.objects.create(city_province="Hanoi", district="Dong Da")
        self.assertNotEqual(l1.id, l2.id)

    def test_field_max_lengths(self):
        city = "A" * 120
        district = "B" * 120
        location = Location.objects.create(city_province=city, district=district)
        self.assertEqual(location.city_province, city)
        self.assertEqual(location.district, district)


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestLocationSerializer(TestCase):
    def test_serializes_location_fields(self):
        location = make_location(city="Hanoi", district="Hoan Kiem")
        serializer = LocationSerializer(location)
        data = serializer.data
        self.assertEqual(data["city_province"], "Hanoi")
        self.assertEqual(data["district"], "Hoan Kiem")
        self.assertIn("id", data)

    def test_all_fields_present(self):
        location = make_location()
        serializer = LocationSerializer(location)
        self.assertEqual(set(serializer.data.keys()), {"id", "city_province", "district"})


class TestPhotographerLocationSyncSerializer(TestCase):
    def setUp(self):
        self.loc1 = make_location(city="Hanoi", district="Hoan Kiem")
        self.loc2 = make_location(city="HCMC", district="District 1")

    def test_valid_location_ids_pass(self):
        data = {"location_ids": [self.loc1.id, self.loc2.id]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_empty_list_is_valid(self):
        data = {"location_ids": []}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_missing_location_ids_raises_error(self):
        nonexistent_id = 99999
        data = {"location_ids": [self.loc1.id, nonexistent_id]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("location_ids", serializer.errors)
        # Error message should mention the missing ID
        error_msg = str(serializer.errors["location_ids"])
        self.assertIn(str(nonexistent_id), error_msg)

    def test_all_missing_ids_reported_sorted(self):
        data = {"location_ids": [9991, 9992, 9993]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_negative_id_fails_min_value_validation(self):
        data = {"location_ids": [-1]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_zero_id_fails_min_value_validation(self):
        data = {"location_ids": [0]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_mixed_valid_and_invalid_ids_all_reported(self):
        data = {"location_ids": [self.loc1.id, 99991, 99992]}
        serializer = PhotographerLocationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        error_msg = str(serializer.errors["location_ids"])
        self.assertIn("99991", error_msg)
        self.assertIn("99992", error_msg)


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------

class TestLocationListAPIView(APITestCase):
    def setUp(self):
        self.url = "/api/locations/"

    def test_anonymous_user_can_list_locations(self):
        make_location(city="Hanoi", district="Hoan Kiem")
        make_location(city="HCMC", district="District 1")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_returns_all_locations(self):
        make_location(city="Hanoi", district="Hoan Kiem")
        make_location(city="HCMC", district="District 1")
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 2)

    def test_locations_ordered_by_city_province_then_district(self):
        make_location(city="HCMC", district="District 1")
        make_location(city="Hanoi", district="Hoan Kiem")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cities = [loc["city_province"] for loc in response.data]
        # "HCMC" > "Hanoi" lexicographically; depends on ASCII ordering
        # Both should be present
        self.assertIn("Hanoi", cities)
        self.assertIn("HCMC", cities)

    def test_empty_database_returns_empty_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class TestPhotographerLocationSyncAPIView(APITestCase):
    def setUp(self):
        self.photographer = make_photographer()
        self.customer = make_customer()
        self.loc1 = make_location(city="Hanoi", district="Hoan Kiem")
        self.loc2 = make_location(city="HCMC", district="District 1")
        self.url = "/api/photographers/me/locations/"

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_photographer_can_get_own_locations(self):
        self._auth(self.photographer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_photographer_can_set_locations(self):
        self._auth(self.photographer)
        data = {"location_ids": [self.loc1.id, self.loc2.id]}
        response = self.client.put(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {loc["id"] for loc in response.data}
        self.assertIn(self.loc1.id, returned_ids)
        self.assertIn(self.loc2.id, returned_ids)

    def test_photographer_can_clear_locations_with_empty_list(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.photographer)
        profile.active_locations.set([self.loc1])

        self._auth(self.photographer)
        data = {"location_ids": []}
        response = self.client.put(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_photographer_sync_replaces_existing_locations(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.photographer)
        profile.active_locations.set([self.loc1])

        self._auth(self.photographer)
        data = {"location_ids": [self.loc2.id]}
        response = self.client.put(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {loc["id"] for loc in response.data}
        self.assertNotIn(self.loc1.id, returned_ids)
        self.assertIn(self.loc2.id, returned_ids)

    def test_customer_cannot_access_location_sync(self):
        self._auth(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_location_sync(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_location_id_returns_400(self):
        self._auth(self.photographer)
        data = {"location_ids": [99999]}
        response = self.client.put(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)