import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking, BookingBid
from locations.models import Location
from user.models import PhotographerProfile, User

from .models import Review
from .permissions import IsBookingParticipant
from .serializers import ReviewSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_customer(username="customer1"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234!",
        role=User.Roles.CUSTOMER,
    )


def make_photographer(username="photo1"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234!",
        role=User.Roles.PHOTOGRAPHER,
    )


def make_location(city="Hanoi", district="Hoan Kiem"):
    return Location.objects.create(city_province=city, district=district)


def make_booking(customer, location, photographer=None, **kwargs):
    defaults = dict(
        title="Test Booking",
        category=Booking.Categories.PERSONAL,
        shoot_date=timezone.localdate() + timedelta(days=10),
        deadline_date=timezone.now() + timedelta(days=5),
        location=location,
        environment=Booking.Environments.OUTDOOR,
        budget_min=Decimal("100.00"),
        budget_max=Decimal("500.00"),
        status=Booking.Status.COMPLETED,
        photographer=photographer,
    )
    defaults.update(kwargs)
    return Booking.objects.create(customer=customer, **defaults)


def make_review(booking, reviewer, reviewee, rating=5):
    return Review.objects.create(
        booking=booking,
        reviewer=reviewer,
        reviewee=reviewee,
        rating=rating,
        comment="Great photographer!",
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestReviewModel(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location, photographer=self.photographer
        )

    def test_str_representation(self):
        review = make_review(self.booking, self.customer, self.photographer)
        self.assertIn("Review<", str(review))

    def test_uuid_primary_key(self):
        review = make_review(self.booking, self.customer, self.photographer)
        self.assertIsInstance(review.id, uuid.UUID)

    def test_one_booking_one_review_constraint(self):
        """A second review on the same booking raises IntegrityError."""
        from django.db import IntegrityError
        make_review(self.booking, self.customer, self.photographer)
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                booking=self.booking,
                reviewer=self.customer,
                reviewee=self.photographer,
                rating=3,
                comment="Duplicate review.",
            )

    def test_ordering_by_created_at_descending(self):
        customer2 = make_customer(username="customer2")
        photographer2 = make_photographer(username="photo2")
        location2 = make_location(city="HCMC", district="D1")
        booking2 = make_booking(customer2, location2, photographer=photographer2)

        r1 = make_review(self.booking, self.customer, self.photographer, rating=5)
        r2 = make_review(booking2, customer2, photographer2, rating=4)
        reviews = list(Review.objects.all())
        self.assertEqual(reviews[0].id, r2.id)
        self.assertEqual(reviews[1].id, r1.id)

    def test_rating_stored_correctly(self):
        review = make_review(self.booking, self.customer, self.photographer, rating=3)
        review.refresh_from_db()
        self.assertEqual(review.rating, 3)

    def test_cascade_delete_when_booking_deleted(self):
        review = make_review(self.booking, self.customer, self.photographer)
        review_id = review.id
        self.booking.delete()
        with self.assertRaises(Review.DoesNotExist):
            Review.objects.get(id=review_id)


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------

class TestIsBookingParticipantPermission(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.other_customer = make_customer(username="customer2")
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location, photographer=self.photographer
        )

    def _make_request(self, method, user, booking_id=None):
        request = MagicMock()
        request.method = method
        request.user = user
        request.data = {}
        if booking_id is not None:
            request.data["booking"] = str(booking_id)
        return request

    def test_non_post_methods_always_allowed(self):
        perm = IsBookingParticipant()
        for method in ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"]:
            request = self._make_request(method, self.customer)
            self.assertTrue(perm.has_permission(request, None))

    def test_booking_customer_can_post(self):
        perm = IsBookingParticipant()
        request = self._make_request("POST", self.customer, self.booking.id)
        self.assertTrue(perm.has_permission(request, None))

    def test_non_customer_cannot_post(self):
        perm = IsBookingParticipant()
        request = self._make_request("POST", self.other_customer, self.booking.id)
        self.assertFalse(perm.has_permission(request, None))

    def test_unauthenticated_post_is_denied(self):
        from django.contrib.auth.models import AnonymousUser
        perm = IsBookingParticipant()
        request = self._make_request("POST", AnonymousUser(), self.booking.id)
        self.assertFalse(perm.has_permission(request, None))

    def test_nonexistent_booking_id_is_denied(self):
        perm = IsBookingParticipant()
        nonexistent_id = uuid.uuid4()
        request = self._make_request("POST", self.customer, nonexistent_id)
        self.assertFalse(perm.has_permission(request, None))

    def test_missing_booking_id_is_denied(self):
        perm = IsBookingParticipant()
        request = self._make_request("POST", self.customer)
        self.assertFalse(perm.has_permission(request, None))

    def test_photographer_cannot_review_own_booking_as_non_customer(self):
        perm = IsBookingParticipant()
        request = self._make_request("POST", self.photographer, self.booking.id)
        self.assertFalse(perm.has_permission(request, None))

    def test_object_permission_reviewer_can_modify(self):
        review = MagicMock()
        review.reviewer_id = self.customer.id
        perm = IsBookingParticipant()
        request = self._make_request("PATCH", self.customer)
        self.assertTrue(perm.has_object_permission(request, None, review))

    def test_object_permission_safe_methods_allowed(self):
        review = MagicMock()
        review.reviewer_id = self.customer.id
        perm = IsBookingParticipant()
        request = self._make_request("GET", self.other_customer)
        self.assertTrue(perm.has_object_permission(request, None, review))

    def test_object_permission_non_reviewer_cannot_modify(self):
        review = MagicMock()
        review.reviewer_id = self.customer.id
        perm = IsBookingParticipant()
        request = self._make_request("PATCH", self.other_customer)
        self.assertFalse(perm.has_object_permission(request, None, review))


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestReviewSerializer(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location, photographer=self.photographer
        )

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_valid_data_passes_validation(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Excellent work!",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rating_below_1_is_invalid(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 0,
            "comment": "Too low.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_rating_above_5_is_invalid(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 6,
            "comment": "Too high.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_rating_boundary_1_is_valid(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 1,
            "comment": "Minimum rating.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rating_boundary_5_is_valid(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Maximum rating.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_non_customer_cannot_review_booking(self):
        other_customer = make_customer(username="other_cust")
        data = {
            "booking": str(self.booking.id),
            "rating": 4,
            "comment": "Not my booking.",
        }
        request = self._make_request(other_customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())

    def test_non_completed_booking_cannot_be_reviewed(self):
        open_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status=Booking.Status.OPEN,
        )
        data = {
            "booking": str(open_booking.id),
            "rating": 5,
            "comment": "Still open.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())

    def test_booking_without_photographer_cannot_be_reviewed(self):
        booking_no_photo = make_booking(
            self.customer, self.location,
            photographer=None,
            status=Booking.Status.COMPLETED,
        )
        data = {
            "booking": str(booking_no_photo.id),
            "rating": 4,
            "comment": "No photographer.",
        }
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())

    def test_duplicate_review_on_same_booking_is_invalid(self):
        # Create first review
        make_review(self.booking, self.customer, self.photographer)

        data = {
            "booking": str(self.booking.id),
            "rating": 3,
            "comment": "Second attempt.",
        }
        request = self._make_request(self.customer)
        # Reload booking so hasattr(booking, 'review') is True
        from bookings.models import Booking as B
        booking = B.objects.get(pk=self.booking.pk)
        serializer = ReviewSerializer(
            data={"booking": str(booking.id), "rating": 3, "comment": "Second"},
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_anonymous_user_is_invalid(self):
        from django.contrib.auth.models import AnonymousUser
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Anonymous.",
        }
        request = MagicMock()
        request.user = AnonymousUser()
        serializer = ReviewSerializer(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())

    def test_read_only_fields(self):
        serializer = ReviewSerializer()
        for field in ["id", "reviewer", "reviewee", "created_at"]:
            self.assertTrue(
                serializer.fields[field].read_only,
                f"Field {field} should be read-only",
            )


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------

class TestUpdatePhotographerRatingSignal(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()

    def _make_completed_booking(self, customer=None, photographer=None, title="B"):
        return make_booking(
            customer or self.customer,
            self.location,
            photographer=photographer or self.photographer,
            title=title,
        )

    def test_signal_creates_photographer_profile_if_not_exists(self):
        booking = self._make_completed_booking()
        make_review(booking, self.customer, self.photographer, rating=4)
        self.assertTrue(
            PhotographerProfile.objects.filter(user=self.photographer).exists()
        )

    def test_signal_updates_rating_avg_on_first_review(self):
        booking = self._make_completed_booking()
        make_review(booking, self.customer, self.photographer, rating=4)

        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(float(profile.rating_avg), 4.0)
        self.assertEqual(profile.total_reviews, 1)

    def test_signal_updates_rating_avg_on_multiple_reviews(self):
        customer2 = make_customer(username="customer2")
        location2 = make_location(city="HCMC", district="D1")

        booking1 = self._make_completed_booking(title="B1")
        booking2 = make_booking(customer2, location2, photographer=self.photographer, title="B2")

        make_review(booking1, self.customer, self.photographer, rating=5)
        make_review(booking2, customer2, self.photographer, rating=3)

        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(float(profile.rating_avg), 4.0)
        self.assertEqual(profile.total_reviews, 2)

    def test_signal_does_not_update_on_save_without_create(self):
        """Signal should only fire on created=True, not on updates."""
        booking = self._make_completed_booking()
        review = make_review(booking, self.customer, self.photographer, rating=5)

        profile = PhotographerProfile.objects.get(user=self.photographer)
        # Manually change profile to verify signal doesn't reset on review update
        profile.total_reviews = 99
        profile.save()

        # Saving the review (update) should NOT trigger the signal recalculation
        review.comment = "Updated comment"
        review.save()

        profile.refresh_from_db()
        self.assertEqual(profile.total_reviews, 99)

    def test_signal_rounds_rating_avg_to_two_decimal_places(self):
        customer2 = make_customer(username="customer2")
        customer3 = make_customer(username="customer3")
        location2 = make_location(city="HCMC", district="D1")
        location3 = make_location(city="Da Nang", district="Hai Chau")

        booking1 = self._make_completed_booking(title="B1")
        booking2 = make_booking(customer2, location2, photographer=self.photographer, title="B2")
        booking3 = make_booking(customer3, location3, photographer=self.photographer, title="B3")

        make_review(booking1, self.customer, self.photographer, rating=5)
        make_review(booking2, customer2, self.photographer, rating=4)
        make_review(booking3, customer3, self.photographer, rating=4)

        profile = PhotographerProfile.objects.get(user=self.photographer)
        # (5+4+4)/3 = 4.333... rounded to 4.33
        self.assertEqual(float(profile.rating_avg), round(13 / 3, 2))


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------

class TestReviewViewSet(APITestCase):
    def setUp(self):
        self.customer = make_customer()
        self.photographer = make_photographer()
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location, photographer=self.photographer
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_create_review_as_booking_customer(self):
        self._auth(self.customer)
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Excellent service!",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["rating"], 5)
        self.assertEqual(str(response.data["reviewer"]), str(self.customer.id))
        self.assertEqual(str(response.data["reviewee"]), str(self.photographer.id))

    def test_create_review_unauthenticated_is_unauthorized(self):
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Test.",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_customer_cannot_create_review(self):
        other_customer = make_customer(username="other_cust")
        self._auth(other_customer)
        data = {
            "booking": str(self.booking.id),
            "rating": 5,
            "comment": "Not my booking.",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_review_for_incomplete_booking_returns_400(self):
        open_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status=Booking.Status.OPEN,
        )
        self._auth(self.customer)
        data = {
            "booking": str(open_booking.id),
            "rating": 5,
            "comment": "Booking not done.",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_review_returns_400(self):
        make_review(self.booking, self.customer, self.photographer)
        self._auth(self.customer)
        data = {
            "booking": str(self.booking.id),
            "rating": 4,
            "comment": "Second review attempt.",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_reviews_is_public(self):
        make_review(self.booking, self.customer, self.photographer)
        response = self.client.get("/api/reviews/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_reviews_anonymous(self):
        make_review(self.booking, self.customer, self.photographer)
        response = self.client.get("/api/reviews/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_photographer_action_returns_reviews_for_photographer(self):
        make_review(self.booking, self.customer, self.photographer)

        other_photographer = make_photographer(username="photo2")
        customer2 = make_customer(username="customer2")
        location2 = make_location(city="HCMC", district="D1")
        booking2 = make_booking(customer2, location2, photographer=other_photographer)
        make_review(booking2, customer2, other_photographer, rating=3)

        url = f"/api/reviews/photographer/{self.photographer.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        reviewees = {r["reviewee"] for r in response.data["results"]}
        self.assertEqual(reviewees, {self.photographer.id})

    def test_photographer_action_empty_when_no_reviews(self):
        url = f"/api/reviews/photographer/{self.photographer.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])

    def test_http_method_put_not_allowed(self):
        """ViewSet limits methods to GET, POST only."""
        review = make_review(self.booking, self.customer, self.photographer)
        self._auth(self.customer)
        response = self.client.put(f"/api/reviews/{review.id}/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_create_review_updates_photographer_rating(self):
        """Integration: creating a review triggers signal that updates profile."""
        self._auth(self.customer)
        data = {
            "booking": str(self.booking.id),
            "rating": 4,
            "comment": "Good work.",
        }
        response = self.client.post("/api/reviews/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(float(profile.rating_avg), 4.0)
        self.assertEqual(profile.total_reviews, 1)