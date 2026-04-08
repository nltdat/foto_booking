import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from locations.models import Location
from user.models import User

from .models import Booking, BookingBid
from .permissions import IsBookingOwner, IsCustomer, IsPhotographer
from .serializers import AcceptBidSerializer, BookingBidSerializer, BookingSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_customer(username="customer1", password="pass1234!"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=User.Roles.CUSTOMER,
    )


def make_photographer(username="photo1", password="pass1234!"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role=User.Roles.PHOTOGRAPHER,
    )


def make_location(city="Hanoi", district="Hoan Kiem"):
    return Location.objects.create(city_province=city, district=district)


def make_booking(customer, location, title="Test Booking", **kwargs):
    defaults = dict(
        title=title,
        category=Booking.Categories.PERSONAL,
        shoot_date=timezone.localdate() + timedelta(days=10),
        deadline_date=timezone.now() + timedelta(days=5),
        location=location,
        environment=Booking.Environments.OUTDOOR,
        budget_min=Decimal("100.00"),
        budget_max=Decimal("500.00"),
    )
    defaults.update(kwargs)
    return Booking.objects.create(customer=customer, **defaults)


def make_booking_bid(booking, photographer, price=Decimal("200.00"), letter="Hi"):
    return BookingBid.objects.create(
        booking=booking,
        photographer=photographer,
        proposed_price=price,
        cover_letter=letter,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestBookingModel(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.location = make_location()

    def test_str_representation(self):
        booking = make_booking(self.customer, self.location, title="Wedding Shoot")
        self.assertIn("Wedding Shoot", str(booking))
        self.assertIn("Booking<", str(booking))

    def test_default_status_is_open(self):
        booking = make_booking(self.customer, self.location)
        self.assertEqual(booking.status, Booking.Status.OPEN)

    def test_uuid_primary_key(self):
        booking = make_booking(self.customer, self.location)
        self.assertIsInstance(booking.id, uuid.UUID)

    def test_photographer_is_nullable(self):
        booking = make_booking(self.customer, self.location)
        self.assertIsNone(booking.photographer)

    def test_categories_choices(self):
        expected = {"PERSONAL", "COUPLE", "EVENT", "WEDDING", "FAMILY"}
        actual = {c[0] for c in Booking.Categories.choices}
        self.assertEqual(actual, expected)

    def test_environments_choices(self):
        expected = {"INDOOR", "OUTDOOR", "STUDIO"}
        actual = {e[0] for e in Booking.Environments.choices}
        self.assertEqual(actual, expected)

    def test_status_choices(self):
        expected = {"OPEN", "MATCHED", "COMPLETED", "CANCELLED"}
        actual = {s[0] for s in Booking.Status.choices}
        self.assertEqual(actual, expected)

    def test_ordering_by_created_at_descending(self):
        b1 = make_booking(self.customer, self.location, title="First")
        b2 = make_booking(self.customer, self.location, title="Second")
        bookings = list(Booking.objects.all())
        # Second created booking should appear first due to -created_at ordering
        self.assertEqual(bookings[0].id, b2.id)
        self.assertEqual(bookings[1].id, b1.id)


class TestBookingBidModel(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def test_str_representation(self):
        bid = make_booking_bid(self.booking, self.photographer)
        self.assertIn("BookingBid<", str(bid))

    def test_default_status_is_pending(self):
        bid = make_booking_bid(self.booking, self.photographer)
        self.assertEqual(bid.status, BookingBid.Status.PENDING)

    def test_uuid_primary_key(self):
        bid = make_booking_bid(self.booking, self.photographer)
        self.assertIsInstance(bid.id, uuid.UUID)

    def test_unique_bid_per_booking_photographer(self):
        """A photographer cannot submit two bids for the same booking."""
        from django.db import IntegrityError
        make_booking_bid(self.booking, self.photographer)
        with self.assertRaises(IntegrityError):
            # Bypass serializer to hit DB constraint directly
            BookingBid.objects.create(
                booking=self.booking,
                photographer=self.photographer,
                proposed_price=Decimal("300.00"),
                cover_letter="Second attempt",
            )

    def test_bid_status_choices(self):
        expected = {"PENDING", "ACCEPTED", "REJECTED"}
        actual = {s[0] for s in BookingBid.Status.choices}
        self.assertEqual(actual, expected)


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------

class TestIsCustomerPermission(TestCase):
    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_allows_customer_role(self):
        user = make_customer()
        request = self._make_request(user)
        perm = IsCustomer()
        self.assertTrue(perm.has_permission(request, None))

    def test_denies_photographer_role(self):
        user = make_photographer()
        request = self._make_request(user)
        perm = IsCustomer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_unauthenticated_user(self):
        user = MagicMock()
        user.is_authenticated = False
        request = self._make_request(user)
        perm = IsCustomer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser
        request = self._make_request(AnonymousUser())
        perm = IsCustomer()
        self.assertFalse(perm.has_permission(request, None))


class TestIsPhotographerPermission(TestCase):
    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_allows_photographer_role(self):
        user = make_photographer()
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertTrue(perm.has_permission(request, None))

    def test_denies_customer_role(self):
        user = make_customer()
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_unauthenticated_user(self):
        user = MagicMock()
        user.is_authenticated = False
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))


class TestIsBookingOwnerPermission(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.other_user = make_customer(username="other_customer")
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_allows_booking_owner(self):
        request = self._make_request(self.customer)
        perm = IsBookingOwner()
        self.assertTrue(perm.has_object_permission(request, None, self.booking))

    def test_denies_non_owner(self):
        request = self._make_request(self.other_user)
        perm = IsBookingOwner()
        self.assertFalse(perm.has_object_permission(request, None, self.booking))

    def test_denies_unauthenticated_user(self):
        user = MagicMock()
        user.is_authenticated = False
        user.id = None
        request = self._make_request(user)
        perm = IsBookingOwner()
        self.assertFalse(perm.has_object_permission(request, None, self.booking))


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestBookingSerializer(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.location = make_location()

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_valid_data_passes_validation(self):
        data = {
            "title": "My Booking",
            "category": "PERSONAL",
            "shoot_date": str(timezone.localdate() + timedelta(days=5)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "OUTDOOR",
            "budget_min": "100.00",
            "budget_max": "500.00",
        }
        serializer = BookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_shoot_date_today_is_invalid(self):
        data = {
            "title": "Invalid",
            "category": "PERSONAL",
            "shoot_date": str(timezone.localdate()),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "OUTDOOR",
            "budget_min": "100.00",
            "budget_max": "500.00",
        }
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("shoot_date", serializer.errors)

    def test_shoot_date_in_past_is_invalid(self):
        data = {
            "title": "Invalid",
            "category": "PERSONAL",
            "shoot_date": str(timezone.localdate() - timedelta(days=1)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "OUTDOOR",
            "budget_min": "100.00",
            "budget_max": "500.00",
        }
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("shoot_date", serializer.errors)

    def test_budget_max_less_than_budget_min_is_invalid(self):
        data = {
            "title": "Invalid Budget",
            "category": "COUPLE",
            "shoot_date": str(timezone.localdate() + timedelta(days=5)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "INDOOR",
            "budget_min": "500.00",
            "budget_max": "100.00",
        }
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("budget_max", serializer.errors)

    def test_budget_max_equal_to_budget_min_is_valid(self):
        data = {
            "title": "Equal Budget",
            "category": "EVENT",
            "shoot_date": str(timezone.localdate() + timedelta(days=5)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "STUDIO",
            "budget_min": "200.00",
            "budget_max": "200.00",
        }
        serializer = BookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_read_only_fields_are_not_writable(self):
        serializer = BookingSerializer()
        for field in ["id", "customer", "status", "created_at", "updated_at"]:
            self.assertTrue(
                serializer.fields[field].read_only,
                f"Field {field} should be read-only",
            )


class TestBookingBidSerializer(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.other_photographer = make_photographer(username="photo2")
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_valid_bid_data(self):
        data = {
            "booking": str(self.booking.id),
            "proposed_price": "250.00",
            "cover_letter": "I am the best photographer.",
        }
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_customer_cannot_bid_own_booking(self):
        data = {
            "booking": str(self.booking.id),
            "proposed_price": "250.00",
            "cover_letter": "Trying to bid own booking.",
        }
        # Pass customer as the request user
        request = self._make_request(self.customer)
        serializer = BookingBidSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_cannot_bid_on_non_open_booking(self):
        self.booking.status = Booking.Status.MATCHED
        self.booking.save()

        data = {
            "booking": str(self.booking.id),
            "proposed_price": "250.00",
            "cover_letter": "Booking is matched.",
        }
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_cannot_bid_twice_on_same_booking(self):
        # Create first bid
        make_booking_bid(self.booking, self.photographer)

        data = {
            "booking": str(self.booking.id),
            "proposed_price": "300.00",
            "cover_letter": "Second attempt.",
        }
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_anonymous_request_is_invalid(self):
        from django.contrib.auth.models import AnonymousUser
        data = {
            "booking": str(self.booking.id),
            "proposed_price": "250.00",
            "cover_letter": "Anonymous bid.",
        }
        request = MagicMock()
        request.user = AnonymousUser()
        serializer = BookingBidSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())

    def test_read_only_fields_are_not_writable(self):
        serializer = BookingBidSerializer()
        for field in ["id", "photographer", "status", "created_at"]:
            self.assertTrue(
                serializer.fields[field].read_only,
                f"Field {field} should be read-only",
            )


class TestAcceptBidSerializer(TestCase):
    def test_valid_uuid_input(self):
        bid_id = uuid.uuid4()
        serializer = AcceptBidSerializer(data={"bid_id": str(bid_id)})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_uuid_input(self):
        serializer = AcceptBidSerializer(data={"bid_id": "not-a-uuid"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("bid_id", serializer.errors)

    def test_missing_bid_id(self):
        serializer = AcceptBidSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("bid_id", serializer.errors)


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------

class TestBookingViewSet(APITestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_create_booking_as_customer_succeeds(self):
        self._auth(self.customer)
        data = {
            "title": "My Event",
            "category": "EVENT",
            "shoot_date": str(timezone.localdate() + timedelta(days=10)),
            "deadline_date": str(timezone.now() + timedelta(days=7)),
            "location": self.location.id,
            "environment": "OUTDOOR",
            "budget_min": "100.00",
            "budget_max": "500.00",
        }
        response = self.client.post("/api/bookings/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["customer"], self.customer.id)
        self.assertEqual(response.data["status"], "OPEN")

    def test_create_booking_as_photographer_is_forbidden(self):
        self._auth(self.photographer)
        data = {
            "title": "Test",
            "category": "PERSONAL",
            "shoot_date": str(timezone.localdate() + timedelta(days=5)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "INDOOR",
            "budget_min": "100.00",
            "budget_max": "200.00",
        }
        response = self.client.post("/api/bookings/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_booking_unauthenticated_is_unauthorized(self):
        data = {
            "title": "Test",
            "category": "PERSONAL",
            "shoot_date": str(timezone.localdate() + timedelta(days=5)),
            "deadline_date": str(timezone.now() + timedelta(days=3)),
            "location": self.location.id,
            "environment": "INDOOR",
            "budget_min": "100.00",
            "budget_max": "200.00",
        }
        response = self.client.post("/api/bookings/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_sees_only_own_bookings(self):
        other_customer = make_customer(username="other_cust")
        booking_mine = make_booking(self.customer, self.location, title="Mine")
        make_booking(other_customer, self.location, title="Theirs")

        self._auth(self.customer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(booking_mine.id), ids)
        self.assertEqual(len(ids), 1)

    def test_photographer_sees_only_open_bookings(self):
        open_booking = make_booking(self.customer, self.location, title="Open")
        matched_booking = make_booking(
            self.customer, self.location, title="Matched",
            status=Booking.Status.MATCHED,
        )

        self._auth(self.photographer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(open_booking.id), ids)
        self.assertNotIn(str(matched_booking.id), ids)

    def test_photographer_can_filter_by_category(self):
        personal_booking = make_booking(
            self.customer, self.location, title="Personal",
            category=Booking.Categories.PERSONAL,
        )
        wedding_booking = make_booking(
            self.customer, self.location, title="Wedding",
            category=Booking.Categories.WEDDING,
        )
        self._auth(self.photographer)
        response = self.client.get("/api/bookings/?category=PERSONAL")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(personal_booking.id), ids)
        self.assertNotIn(str(wedding_booking.id), ids)

    def test_photographer_can_filter_by_location(self):
        location2 = make_location(city="HCMC", district="District 1")
        b1 = make_booking(self.customer, self.location, title="Hanoi")
        b2 = make_booking(self.customer, location2, title="HCMC")

        self._auth(self.photographer)
        response = self.client.get(f"/api/bookings/?location={self.location.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(b1.id), ids)
        self.assertNotIn(str(b2.id), ids)

    def test_accept_bid_sets_booking_matched(self):
        booking = make_booking(self.customer, self.location)
        bid = make_booking_bid(booking, self.photographer)

        self._auth(self.customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(url, {"bid_id": str(bid.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        booking.refresh_from_db()
        bid.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.MATCHED)
        self.assertEqual(booking.photographer, self.photographer)
        self.assertEqual(bid.status, BookingBid.Status.ACCEPTED)

    def test_accept_bid_rejects_other_bids(self):
        other_photographer = make_photographer(username="photo2")
        booking = make_booking(self.customer, self.location)
        accepted_bid = make_booking_bid(booking, self.photographer)
        rejected_bid = make_booking_bid(booking, other_photographer)

        self._auth(self.customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(url, {"bid_id": str(accepted_bid.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        rejected_bid.refresh_from_db()
        self.assertEqual(rejected_bid.status, BookingBid.Status.REJECTED)

    def test_accept_bid_missing_bid_id_returns_400(self):
        booking = make_booking(self.customer, self.location)
        self._auth(self.customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_bid_with_invalid_bid_id_returns_400(self):
        booking = make_booking(self.customer, self.location)
        self._auth(self.customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(
            url, {"bid_id": str(uuid.uuid4())}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_bid_on_matched_booking_returns_400(self):
        booking = make_booking(
            self.customer, self.location, status=Booking.Status.MATCHED
        )
        bid = make_booking_bid(booking, self.photographer)
        self._auth(self.customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(url, {"bid_id": str(bid.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_owner_cannot_accept_bid(self):
        other_customer = make_customer(username="other_cust")
        booking = make_booking(self.customer, self.location)
        bid = make_booking_bid(booking, self.photographer)

        self._auth(other_customer)
        url = f"/api/bookings/{booking.id}/accept_bid/"
        response = self.client.post(url, {"bid_id": str(bid.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestBookingBidViewSet(APITestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_photographer_can_create_bid(self):
        self._auth(self.photographer)
        data = {
            "booking": str(self.booking.id),
            "proposed_price": "300.00",
            "cover_letter": "I'll do a great job!",
        }
        response = self.client.post("/api/booking-bids/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["photographer"], self.photographer.id)

    def test_customer_cannot_create_bid(self):
        self._auth(self.customer)
        data = {
            "booking": str(self.booking.id),
            "proposed_price": "300.00",
            "cover_letter": "Customer bidding.",
        }
        response = self.client.post("/api/booking-bids/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photographer_sees_only_own_bids(self):
        other_photographer = make_photographer(username="photo2")
        bid_mine = make_booking_bid(self.booking, self.photographer)
        bid_theirs = make_booking_bid(self.booking, other_photographer)

        self._auth(self.photographer)
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(bid_mine.id), ids)
        self.assertNotIn(str(bid_theirs.id), ids)

    def test_customer_sees_bids_for_own_bookings(self):
        other_customer = make_customer(username="other_cust")
        other_booking = make_booking(other_customer, self.location)
        bid_for_mine = make_booking_bid(self.booking, self.photographer)
        bid_for_other = make_booking_bid(other_booking, self.photographer)

        self._auth(self.customer)
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [b["id"] for b in response.data["results"]]
        self.assertIn(str(bid_for_mine.id), ids)
        self.assertNotIn(str(bid_for_other.id), ids)

    def test_unauthenticated_cannot_list_bids(self):
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)