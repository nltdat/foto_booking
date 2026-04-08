import datetime
import uuid

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from bookings.models import Booking
from locations.models import Location
from user.models import PhotographerProfile, User

from .models import Review
from .permissions import IsBookingParticipant
from .serializers import ReviewSerializer


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


def make_location():
    return Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")


def make_booking(customer, location, photographer=None, status_val=Booking.Status.OPEN):
    return Booking.objects.create(
        customer=customer,
        photographer=photographer,
        title="Test Booking",
        category=Booking.Categories.PERSONAL,
        shoot_date=timezone.localdate() + datetime.timedelta(days=7),
        deadline_date=timezone.now() + datetime.timedelta(days=5),
        location=location,
        environment=Booking.Environments.OUTDOOR,
        requires_makeup=False,
        budget_min="500.00",
        budget_max="1000.00",
        status=status_val,
    )


def make_review(booking, reviewer, reviewee, rating=5, comment="Great!"):
    return Review.objects.create(
        booking=booking,
        reviewer=reviewer,
        reviewee=reviewee,
        rating=rating,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class ReviewModelTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1")
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )

    def test_str_representation(self):
        review = make_review(self.booking, self.customer, self.photographer)
        self.assertIn("Review<", str(review))

    def test_uuid_primary_key(self):
        review = make_review(self.booking, self.customer, self.photographer)
        self.assertIsInstance(review.pk, uuid.UUID)

    def test_one_review_per_booking(self):
        from django.db import IntegrityError

        make_review(self.booking, self.customer, self.photographer)
        with self.assertRaises(IntegrityError):
            make_review(self.booking, self.customer, self.photographer, rating=3)

    def test_rating_values(self):
        for rating in [1, 2, 3, 4, 5]:
            booking = make_booking(
                self.customer, self.location,
                photographer=self.photographer,
                status_val=Booking.Status.COMPLETED,
            )
            review = make_review(booking, self.customer, self.photographer, rating=rating)
            self.assertEqual(review.rating, rating)

    def test_cascade_delete_on_booking_delete(self):
        review = make_review(self.booking, self.customer, self.photographer)
        review_id = review.pk
        self.booking.delete()
        self.assertFalse(Review.objects.filter(pk=review_id).exists())

    def test_cascade_delete_on_reviewer_delete(self):
        review = make_review(self.booking, self.customer, self.photographer)
        review_id = review.pk
        self.customer.delete()
        self.assertFalse(Review.objects.filter(pk=review_id).exists())

    def test_ordering_by_created_at_desc(self):
        booking2 = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        r1 = make_review(self.booking, self.customer, self.photographer, rating=5)
        r2 = make_review(booking2, self.customer, self.photographer, rating=4)
        reviews = list(Review.objects.all())
        self.assertEqual(reviews[0].pk, r2.pk)


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------

class IsBookingParticipantPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsBookingParticipant()
        self.customer = make_user("customer1")
        self.other_user = make_user("other", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()
        self.booking = make_booking(
            self.customer, self.location,
            photographer=self.other_user,
            status_val=Booking.Status.COMPLETED,
        )

    def _make_post_request(self, user, booking_id):
        request = self.factory.post("/", {"booking": str(booking_id)})
        request.user = user
        # DRF doesn't parse request.data from APIRequestFactory by default
        request.data = {"booking": str(booking_id)}
        return request

    def _make_get_request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def test_get_always_allowed(self):
        request = self._make_get_request(self.other_user)
        self.assertTrue(self.perm.has_permission(request, None))

    def test_booking_customer_allowed_for_post(self):
        request = self._make_post_request(self.customer, self.booking.pk)
        self.assertTrue(self.perm.has_permission(request, None))

    def test_non_customer_denied_for_post(self):
        request = self._make_post_request(self.other_user, self.booking.pk)
        self.assertFalse(self.perm.has_permission(request, None))

    def test_nonexistent_booking_denied(self):
        request = self._make_post_request(self.customer, uuid.uuid4())
        self.assertFalse(self.perm.has_permission(request, None))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.post("/", {"booking": str(self.booking.pk)})
        request.user = AnonymousUser()
        request.data = {"booking": str(self.booking.pk)}
        self.assertFalse(self.perm.has_permission(request, None))

    def test_missing_booking_id_denied(self):
        request = self.factory.post("/", {})
        request.user = self.customer
        request.data = {}
        self.assertFalse(self.perm.has_permission(request, None))

    def test_has_object_permission_safe_methods(self):
        review = make_review(self.booking, self.customer, self.other_user)
        request = self._make_get_request(self.other_user)
        self.assertTrue(self.perm.has_object_permission(request, None, review))

    def test_has_object_permission_reviewer_allowed(self):
        review = make_review(self.booking, self.customer, self.other_user)
        request = self.factory.delete("/")
        request.user = self.customer
        self.assertTrue(self.perm.has_object_permission(request, None, review))

    def test_has_object_permission_non_reviewer_denied(self):
        review = make_review(self.booking, self.customer, self.other_user)
        request = self.factory.delete("/")
        request.user = self.other_user
        self.assertFalse(self.perm.has_object_permission(request, None, review))


# ---------------------------------------------------------------------------
# Serializer Tests
# ---------------------------------------------------------------------------

class ReviewSerializerTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = make_user("customer1")
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.other_customer = make_user("customer2")
        self.location = make_location()
        self.completed_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        self.open_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.OPEN,
        )

    def _make_request(self, user):
        request = self.factory.post("/")
        request.user = user
        return request

    def test_valid_review_passes(self):
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Excellent!",
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rating_below_1_fails(self):
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "rating": 0,
                "comment": "Bad",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_rating_above_5_fails(self):
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "rating": 6,
                "comment": "Too high",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_non_customer_of_booking_fails(self):
        request = self._make_request(self.other_customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Not my booking",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_non_completed_booking_fails(self):
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.open_booking.pk),
                "rating": 5,
                "comment": "Not done",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_booking_without_photographer_fails(self):
        booking_no_photo = make_booking(
            self.customer, self.location,
            photographer=None,
            status_val=Booking.Status.COMPLETED,
        )
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(booking_no_photo.pk),
                "rating": 4,
                "comment": "No photographer",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_duplicate_review_fails(self):
        # Create first review
        Review.objects.create(
            booking=self.completed_booking,
            reviewer=self.customer,
            reviewee=self.photographer,
            rating=4,
            comment="First",
        )
        # Mark booking as having a review by accessing fresh from DB
        booking_from_db = Booking.objects.prefetch_related("review").get(
            pk=self.completed_booking.pk
        )
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(booking_from_db.pk),
                "rating": 5,
                "comment": "Second",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_anonymous_request_fails(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.post("/")
        request.user = AnonymousUser()
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Anonymous",
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())

    def test_read_only_fields_not_writable(self):
        request = self._make_request(self.customer)
        serializer = ReviewSerializer(
            data={
                "booking": str(self.completed_booking.pk),
                "reviewer": str(self.customer.pk),
                "reviewee": str(self.photographer.pk),
                "rating": 5,
                "comment": "Test",
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("reviewer", serializer.validated_data)
        self.assertNotIn("reviewee", serializer.validated_data)


# ---------------------------------------------------------------------------
# Signal Tests
# ---------------------------------------------------------------------------

class ReviewSignalTest(TestCase):
    def setUp(self):
        self.customer = make_user("customer1")
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.location = make_location()

    def _make_completed_booking(self):
        return make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )

    def test_signal_creates_profile_if_not_exists(self):
        self.assertFalse(
            PhotographerProfile.objects.filter(user=self.photographer).exists()
        )
        booking = self._make_completed_booking()
        make_review(booking, self.customer, self.photographer, rating=5)
        self.assertTrue(
            PhotographerProfile.objects.filter(user=self.photographer).exists()
        )

    def test_signal_updates_total_reviews(self):
        booking = self._make_completed_booking()
        make_review(booking, self.customer, self.photographer, rating=5)
        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(profile.total_reviews, 1)

    def test_signal_updates_rating_avg_single_review(self):
        booking = self._make_completed_booking()
        make_review(booking, self.customer, self.photographer, rating=4)
        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(float(profile.rating_avg), 4.0)

    def test_signal_updates_rating_avg_multiple_reviews(self):
        customer2 = make_user("customer2")
        booking1 = self._make_completed_booking()
        booking2 = make_booking(
            customer2, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        make_review(booking1, self.customer, self.photographer, rating=4)
        make_review(booking2, customer2, self.photographer, rating=2)
        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(profile.total_reviews, 2)
        self.assertEqual(float(profile.rating_avg), 3.0)

    def test_signal_rounds_rating_avg_to_two_decimals(self):
        customer2 = make_user("customer2")
        customer3 = make_user("customer3")
        booking1 = self._make_completed_booking()
        booking2 = make_booking(
            customer2, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        booking3 = make_booking(
            customer3, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        make_review(booking1, self.customer, self.photographer, rating=5)
        make_review(booking2, customer2, self.photographer, rating=4)
        make_review(booking3, customer3, self.photographer, rating=4)
        profile = PhotographerProfile.objects.get(user=self.photographer)
        # avg = (5+4+4)/3 = 13/3 = 4.333... -> 4.33
        self.assertEqual(float(profile.rating_avg), 4.33)

    def test_signal_only_fires_on_create(self):
        booking = self._make_completed_booking()
        review = make_review(booking, self.customer, self.photographer, rating=5)
        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(profile.total_reviews, 1)

        # Update the review (not create) - signal should not change total_reviews
        review.comment = "Updated comment"
        review.save()
        profile.refresh_from_db()
        self.assertEqual(profile.total_reviews, 1)


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------

class ReviewViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = make_user("customer1")
        self.photographer = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.other_customer = make_user("customer2")
        self.location = make_location()
        self.completed_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.COMPLETED,
        )
        self.open_booking = make_booking(
            self.customer, self.location,
            photographer=self.photographer,
            status_val=Booking.Status.OPEN,
        )

    # --- List ---

    def test_list_is_public(self):
        response = self.client.get("/api/reviews/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_reviews(self):
        make_review(self.completed_booking, self.customer, self.photographer)
        response = self.client.get("/api/reviews/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # --- Create ---

    def test_create_requires_authentication(self):
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Great!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_booking_customer_can_create_review(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Excellent service!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["rating"], 5)
        self.assertEqual(str(response.data["reviewer"]), str(self.customer.pk))
        self.assertEqual(str(response.data["reviewee"]), str(self.photographer.pk))

    def test_non_customer_cannot_create_review(self):
        self.client.force_authenticate(user=self.other_customer)
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 5,
                "comment": "Not my booking",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_review_non_completed_booking(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.open_booking.pk),
                "rating": 5,
                "comment": "Not done yet",
            },
            format="json",
        )
        # IsBookingParticipant allows POST for booking customer, but serializer validation fails
        # The permission checks customer ownership, but serializer checks COMPLETED status
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        ])

    def test_cannot_create_duplicate_review(self):
        make_review(self.completed_booking, self.customer, self.photographer)
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 4,
                "comment": "Duplicate",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rating_out_of_range_returns_400(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 10,
                "comment": "Too high",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_review_triggers_rating_update(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post(
            "/api/reviews/",
            {
                "booking": str(self.completed_booking.pk),
                "rating": 4,
                "comment": "Good",
            },
            format="json",
        )
        profile = PhotographerProfile.objects.get(user=self.photographer)
        self.assertEqual(profile.total_reviews, 1)
        self.assertEqual(float(profile.rating_avg), 4.0)

    # --- Photographer action ---

    def test_photographer_reviews_endpoint_is_public(self):
        response = self.client.get(
            f"/api/reviews/photographer/{self.photographer.pk}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_photographer_reviews_returns_correct_reviews(self):
        other_photographer = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        booking_for_other = make_booking(
            self.customer, self.location,
            photographer=other_photographer,
            status_val=Booking.Status.COMPLETED,
        )
        r1 = make_review(self.completed_booking, self.customer, self.photographer, rating=5)
        make_review(booking_for_other, self.customer, other_photographer, rating=3)

        response = self.client.get(
            f"/api/reviews/photographer/{self.photographer.pk}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(r1.pk), ids)
        self.assertEqual(len(ids), 1)

    def test_photographer_reviews_empty_for_unknown_photographer(self):
        response = self.client.get(
            f"/api/reviews/photographer/{uuid.uuid4()}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    # --- HTTP method restrictions ---

    def test_put_method_not_allowed(self):
        review = make_review(self.completed_booking, self.customer, self.photographer)
        self.client.force_authenticate(user=self.customer)
        response = self.client.put(
            f"/api/reviews/{review.pk}/",
            {"rating": 3, "comment": "Update"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_method_not_allowed(self):
        review = make_review(self.completed_booking, self.customer, self.photographer)
        self.client.force_authenticate(user=self.customer)
        response = self.client.delete(f"/api/reviews/{review.pk}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)