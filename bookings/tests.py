import datetime
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from locations.models import Location
from user.models import User

from .models import Booking, BookingBid
from .permissions import IsBookingOwner, IsCustomer, IsPhotographer
from .serializers import AcceptBidSerializer, BookingBidSerializer, BookingSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username, role=User.Roles.CUSTOMER, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="pass123",
        role=role,
        **kwargs,
    )


def make_location(city="Ha Noi", district="Hoan Kiem"):
    return Location.objects.create(city_province=city, district=district)


def make_booking(customer, location, **kwargs):
    defaults = {
        "title": "Test Booking",
        "category": Booking.Categories.PERSONAL,
        "shoot_date": timezone.localdate() + datetime.timedelta(days=7),
        "deadline_date": timezone.now() + datetime.timedelta(days=5),
        "environment": Booking.Environments.OUTDOOR,
        "requires_makeup": False,
        "budget_min": "500.00",
        "budget_max": "1000.00",
        "status": Booking.Status.OPEN,
    }
    defaults.update(kwargs)
    return Booking.objects.create(customer=customer, location=location, **defaults)


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class BookingModelTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1")
        self.location = make_location()

    def test_str_representation(self):
        booking = make_booking(self.customer, self.location, title="My Wedding")
        self.assertIn("My Wedding", str(booking))
        self.assertIn("Booking<", str(booking))

    def test_default_status_is_open(self):
        booking = make_booking(self.customer, self.location)
        self.assertEqual(booking.status, Booking.Status.OPEN)

    def test_uuid_primary_key(self):
        booking = make_booking(self.customer, self.location)
        self.assertIsInstance(booking.pk, uuid.UUID)

    def test_photographer_nullable(self):
        booking = make_booking(self.customer, self.location)
        self.assertIsNone(booking.photographer)

    def test_categories_choices(self):
        choices = [c[0] for c in Booking.Categories.choices]
        self.assertIn("PERSONAL", choices)
        self.assertIn("COUPLE", choices)
        self.assertIn("EVENT", choices)
        self.assertIn("WEDDING", choices)
        self.assertIn("FAMILY", choices)

    def test_environments_choices(self):
        choices = [c[0] for c in Booking.Environments.choices]
        self.assertIn("INDOOR", choices)
        self.assertIn("OUTDOOR", choices)
        self.assertIn("STUDIO", choices)

    def test_status_choices(self):
        choices = [c[0] for c in Booking.Status.choices]
        self.assertIn("OPEN", choices)
        self.assertIn("MATCHED", choices)
        self.assertIn("COMPLETED", choices)
        self.assertIn("CANCELLED", choices)

    def test_ordering_by_created_at_desc(self):
        b1 = make_booking(self.customer, self.location, title="First")
        b2 = make_booking(self.customer, self.location, title="Second")
        bookings = list(Booking.objects.all())
        # The most recently created should come first
        self.assertEqual(bookings[0].pk, b2.pk)

    def test_cascade_delete_on_customer_delete(self):
        booking = make_booking(self.customer, self.location)
        booking_id = booking.pk
        self.customer.delete()
        self.assertFalse(Booking.objects.filter(pk=booking_id).exists())


class BookingBidModelTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1")
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def test_str_representation(self):
        bid = BookingBid.objects.create(
            booking=self.booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I am great",
        )
        self.assertIn("BookingBid<", str(bid))

    def test_default_status_is_pending(self):
        bid = BookingBid.objects.create(
            booking=self.booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I am great",
        )
        self.assertEqual(bid.status, BookingBid.Status.PENDING)

    def test_uuid_primary_key(self):
        bid = BookingBid.objects.create(
            booking=self.booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I am great",
        )
        self.assertIsInstance(bid.pk, uuid.UUID)

    def test_unique_constraint_booking_photographer(self):
        from django.db import IntegrityError

        BookingBid.objects.create(
            booking=self.booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="First bid",
        )
        with self.assertRaises(IntegrityError):
            BookingBid.objects.create(
                booking=self.booking,
                photographer=self.photographer,
                proposed_price="900.00",
                cover_letter="Second bid",
            )

    def test_cascade_delete_on_booking_delete(self):
        bid = BookingBid.objects.create(
            booking=self.booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I am great",
        )
        bid_id = bid.pk
        self.booking.delete()
        self.assertFalse(BookingBid.objects.filter(pk=bid_id).exists())


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------

class IsCustomerPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsCustomer()
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)

    def _make_request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_customer_has_permission(self):
        request = self._make_request(self.customer)
        self.assertTrue(self.perm.has_permission(request, None))

    def test_photographer_denied(self):
        request = self._make_request(self.photographer)
        self.assertFalse(self.perm.has_permission(request, None))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(AnonymousUser())
        self.assertFalse(self.perm.has_permission(request, None))


class IsPhotographerPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsPhotographer()
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)

    def _make_request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_photographer_has_permission(self):
        request = self._make_request(self.photographer)
        self.assertTrue(self.perm.has_permission(request, None))

    def test_customer_denied(self):
        request = self._make_request(self.customer)
        self.assertFalse(self.perm.has_permission(request, None))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(AnonymousUser())
        self.assertFalse(self.perm.has_permission(request, None))


class IsBookingOwnerPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsBookingOwner()
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.other_user = make_user("other", role=User.Roles.CUSTOMER)
        self.location = make_location()
        self.booking = make_booking(self.customer, self.location)

    def _make_request(self, user):
        request = self.factory.post("/")
        request.user = user
        return request

    def test_booking_owner_has_object_permission(self):
        request = self._make_request(self.customer)
        self.assertTrue(self.perm.has_object_permission(request, None, self.booking))

    def test_non_owner_denied_object_permission(self):
        request = self._make_request(self.other_user)
        self.assertFalse(self.perm.has_object_permission(request, None, self.booking))

    def test_unauthenticated_denied_object_permission(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(AnonymousUser())
        self.assertFalse(self.perm.has_object_permission(request, None, self.booking))


# ---------------------------------------------------------------------------
# Serializer Tests
# ---------------------------------------------------------------------------

class BookingSerializerTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1")
        self.location = make_location()
        self.future_date = timezone.localdate() + datetime.timedelta(days=10)
        self.valid_data = {
            "title": "My Booking",
            "category": Booking.Categories.PERSONAL,
            "shoot_date": self.future_date,
            "deadline_date": timezone.now() + datetime.timedelta(days=5),
            "location": self.location.pk,
            "environment": Booking.Environments.OUTDOOR,
            "requires_makeup": False,
            "budget_min": "500.00",
            "budget_max": "1000.00",
        }

    def test_valid_data_passes(self):
        serializer = BookingSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_shoot_date_today_fails(self):
        data = self.valid_data.copy()
        data["shoot_date"] = timezone.localdate()
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("shoot_date", serializer.errors)

    def test_shoot_date_in_past_fails(self):
        data = self.valid_data.copy()
        data["shoot_date"] = timezone.localdate() - datetime.timedelta(days=1)
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("shoot_date", serializer.errors)

    def test_budget_max_less_than_min_fails(self):
        data = self.valid_data.copy()
        data["budget_min"] = "1000.00"
        data["budget_max"] = "500.00"
        serializer = BookingSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("budget_max", serializer.errors)

    def test_budget_max_equal_to_min_passes(self):
        data = self.valid_data.copy()
        data["budget_min"] = "500.00"
        data["budget_max"] = "500.00"
        serializer = BookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_read_only_fields_not_writable(self):
        data = self.valid_data.copy()
        data["status"] = Booking.Status.COMPLETED
        data["customer"] = self.customer.pk
        serializer = BookingSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # customer and status should not be in validated_data (read_only)
        self.assertNotIn("customer", serializer.validated_data)
        self.assertNotIn("status", serializer.validated_data)


class BookingBidSerializerTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.other_photographer = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()
        self.open_booking = make_booking(self.customer, self.location)
        self.matched_booking = make_booking(
            self.customer, self.location,
            title="Matched",
            status=Booking.Status.MATCHED,
        )
        self.factory = APIRequestFactory()

    def _make_request(self, user):
        request = self.factory.post("/")
        request.user = user
        return request

    def test_valid_bid_passes(self):
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(
            data={
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "I can do it",
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_customer_cannot_bid_own_booking(self):
        request = self._make_request(self.customer)
        serializer = BookingBidSerializer(
            data={
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "Self bid",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_cannot_bid_non_open_booking(self):
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(
            data={
                "booking": str(self.matched_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "Too late",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_duplicate_bid_fails(self):
        # Create first bid
        BookingBid.objects.create(
            booking=self.open_booking,
            photographer=self.photographer,
            proposed_price="700.00",
            cover_letter="First bid",
        )
        request = self._make_request(self.photographer)
        serializer = BookingBidSerializer(
            data={
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "Second bid",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("booking", serializer.errors)

    def test_anonymous_request_fails(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.post("/")
        request.user = AnonymousUser()
        serializer = BookingBidSerializer(
            data={
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "Anonymous",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())


class AcceptBidSerializerTest(TestCase):
    def test_valid_uuid(self):
        some_uuid = str(uuid.uuid4())
        serializer = AcceptBidSerializer(data={"bid_id": some_uuid})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_uuid_fails(self):
        serializer = AcceptBidSerializer(data={"bid_id": "not-a-uuid"})
        self.assertFalse(serializer.is_valid())

    def test_missing_bid_id_fails(self):
        serializer = AcceptBidSerializer(data={})
        self.assertFalse(serializer.is_valid())


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------

class BookingViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.customer2 = make_user("customer2", role=User.Roles.CUSTOMER)
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()

    def _create_booking(self, customer=None, **kwargs):
        customer = customer or self.customer
        return make_booking(customer, self.location, **kwargs)

    # --- List ---

    def test_list_requires_authentication(self):
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_sees_only_own_bookings(self):
        self._create_booking(self.customer, title="My Booking")
        self._create_booking(self.customer2, title="Other Booking")
        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "My Booking")

    def test_photographer_sees_only_open_bookings(self):
        self._create_booking(self.customer, title="Open Booking", status=Booking.Status.OPEN)
        self._create_booking(self.customer, title="Matched Booking", status=Booking.Status.MATCHED)
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Open Booking")

    def test_photographer_filter_by_location(self):
        loc2 = Location.objects.create(city_province="Da Nang", district="Hai Chau")
        self._create_booking(self.customer, title="Ha Noi Booking", location=self.location)
        self._create_booking(self.customer, title="Da Nang Booking", location=loc2)
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get(f"/api/bookings/?location={self.location.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Ha Noi Booking")

    def test_photographer_filter_by_category(self):
        self._create_booking(self.customer, title="Wedding", category=Booking.Categories.WEDDING)
        self._create_booking(self.customer, title="Event", category=Booking.Categories.EVENT)
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get("/api/bookings/?category=WEDDING")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Wedding")

    # --- Create ---

    def test_customer_can_create_booking(self):
        self.client.force_authenticate(user=self.customer)
        future = (timezone.localdate() + datetime.timedelta(days=10)).isoformat()
        response = self.client.post(
            "/api/bookings/",
            {
                "title": "New Booking",
                "category": "PERSONAL",
                "shoot_date": future,
                "deadline_date": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
                "location": self.location.pk,
                "environment": "OUTDOOR",
                "requires_makeup": False,
                "budget_min": "500.00",
                "budget_max": "1000.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "New Booking")
        self.assertEqual(str(response.data["customer"]), str(self.customer.pk))

    def test_photographer_cannot_create_booking(self):
        self.client.force_authenticate(user=self.photographer)
        future = (timezone.localdate() + datetime.timedelta(days=10)).isoformat()
        response = self.client.post(
            "/api/bookings/",
            {
                "title": "Bad",
                "category": "PERSONAL",
                "shoot_date": future,
                "deadline_date": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
                "location": self.location.pk,
                "environment": "OUTDOOR",
                "requires_makeup": False,
                "budget_min": "500.00",
                "budget_max": "1000.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_booking(self):
        future = (timezone.localdate() + datetime.timedelta(days=10)).isoformat()
        response = self.client.post(
            "/api/bookings/",
            {
                "title": "Bad",
                "category": "PERSONAL",
                "shoot_date": future,
                "deadline_date": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
                "location": self.location.pk,
                "environment": "OUTDOOR",
                "requires_makeup": False,
                "budget_min": "500.00",
                "budget_max": "1000.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Accept Bid ---

    def test_accept_bid_sets_booking_matched(self):
        booking = self._create_booking(self.customer)
        bid = BookingBid.objects.create(
            booking=booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I can do it",
        )
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": str(bid.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.MATCHED)
        bid.refresh_from_db()
        self.assertEqual(bid.status, BookingBid.Status.ACCEPTED)

    def test_accept_bid_rejects_other_bids(self):
        booking = self._create_booking(self.customer)
        photo2 = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        bid1 = BookingBid.objects.create(
            booking=booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="Bid 1",
        )
        bid2 = BookingBid.objects.create(
            booking=booking,
            photographer=photo2,
            proposed_price="700.00",
            cover_letter="Bid 2",
        )
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": str(bid1.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bid2.refresh_from_db()
        self.assertEqual(bid2.status, BookingBid.Status.REJECTED)

    def test_accept_bid_sets_photographer_on_booking(self):
        booking = self._create_booking(self.customer)
        bid = BookingBid.objects.create(
            booking=booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I can do it",
        )
        self.client.force_authenticate(user=self.customer)
        self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": str(bid.pk)},
            format="json",
        )
        booking.refresh_from_db()
        self.assertEqual(booking.photographer, self.photographer)

    def test_accept_bid_requires_ownership(self):
        booking = self._create_booking(self.customer)
        bid = BookingBid.objects.create(
            booking=booking,
            photographer=self.photographer,
            proposed_price="800.00",
            cover_letter="I can do it",
        )
        self.client.force_authenticate(user=self.customer2)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": str(bid.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accept_bid_missing_bid_id_returns_400(self):
        booking = self._create_booking(self.customer)
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_bid_non_open_booking_returns_400(self):
        booking = self._create_booking(self.customer, status=Booking.Status.MATCHED)
        some_uuid = str(uuid.uuid4())
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": some_uuid},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_bid_wrong_booking_id_returns_400(self):
        booking = self._create_booking(self.customer)
        wrong_bid_id = str(uuid.uuid4())
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/bookings/{booking.pk}/accept_bid/",
            {"bid_id": wrong_bid_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BookingBidViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user("customer1", role=User.Roles.CUSTOMER)
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.photographer2 = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()
        self.open_booking = make_booking(self.customer, self.location)

    # --- Create ---

    def test_photographer_can_create_bid(self):
        self.client.force_authenticate(user=self.photographer)
        response = self.client.post(
            "/api/booking-bids/",
            {
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "I am great",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data["photographer"]), str(self.photographer.pk))

    def test_customer_cannot_create_bid(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/booking-bids/",
            {
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "I am great",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_bid(self):
        response = self.client.post(
            "/api/booking-bids/",
            {
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "I am great",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_photographer_cannot_bid_twice(self):
        self.client.force_authenticate(user=self.photographer)
        self.client.post(
            "/api/booking-bids/",
            {
                "booking": str(self.open_booking.pk),
                "proposed_price": "750.00",
                "cover_letter": "First",
            },
            format="json",
        )
        response = self.client.post(
            "/api/booking-bids/",
            {
                "booking": str(self.open_booking.pk),
                "proposed_price": "800.00",
                "cover_letter": "Second",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- List ---

    def test_list_requires_authentication(self):
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_photographer_sees_only_own_bids(self):
        BookingBid.objects.create(
            booking=self.open_booking,
            photographer=self.photographer,
            proposed_price="750.00",
            cover_letter="My bid",
        )
        BookingBid.objects.create(
            booking=self.open_booking,
            photographer=self.photographer2,
            proposed_price="600.00",
            cover_letter="Other bid",
        )
        self.client.force_authenticate(user=self.photographer)
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]["photographer"]), str(self.photographer.pk))

    def test_customer_sees_only_bids_for_own_bookings(self):
        customer2 = make_user("customer2", role=User.Roles.CUSTOMER)
        booking2 = make_booking(customer2, self.location, title="Other Booking")
        BookingBid.objects.create(
            booking=self.open_booking,
            photographer=self.photographer,
            proposed_price="750.00",
            cover_letter="For customer1",
        )
        BookingBid.objects.create(
            booking=booking2,
            photographer=self.photographer2,
            proposed_price="600.00",
            cover_letter="For customer2",
        )
        self.client.force_authenticate(user=self.customer)
        response = self.client.get("/api/booking-bids/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)