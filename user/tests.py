from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking
from locations.models import Location
from portfolio.models import Portfolio

from .models import PhotographerProfile, User
from .permissions import IsPhotographer
from .email_service import EmailService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username="testuser", role=User.Roles.CUSTOMER):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass1234!",
        role=role,
    )


# ---------------------------------------------------------------------------
# IsPhotographer permission tests (moved from user/views.py to user/permissions.py)
# ---------------------------------------------------------------------------

class TestIsPhotographerPermission(TestCase):
    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_allows_photographer_role(self):
        user = make_user(role=User.Roles.PHOTOGRAPHER)
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertTrue(perm.has_permission(request, None))

    def test_denies_customer_role(self):
        user = make_user(role=User.Roles.CUSTOMER)
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_admin_role(self):
        user = make_user(username="admin1", role=User.Roles.ADMIN)
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_unauthenticated_user(self):
        user = MagicMock()
        user.is_authenticated = False
        request = self._make_request(user)
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser
        request = self._make_request(AnonymousUser())
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_denies_none_user(self):
        request = MagicMock()
        request.user = None
        perm = IsPhotographer()
        self.assertFalse(perm.has_permission(request, None))

    def test_permission_message(self):
        perm = IsPhotographer()
        self.assertIsNotNone(perm.message)
        self.assertIsInstance(perm.message, str)


class ForgotPasswordAPITests(APITestCase):
    def setUp(self):
        self.user = make_user(username="forgotuser")
        self.url = reverse("auth-forgot-password")

    def test_forgot_password_sends_email_when_user_exists(self):
        response = self.client.post(
            self.url,
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Yeu cau dat lai mat khau", mail.outbox[0].subject)
        self.assertIn(settings.FRONTEND_RESET_PASSWORD_URL, mail.outbox[0].body)

    def test_forgot_password_returns_success_when_user_not_found(self):
        response = self.client.post(
            self.url,
            {"email": "not-exists@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)


class ResetPasswordAPITests(APITestCase):
    def setUp(self):
        self.user = make_user(username="resetuser")
        self.url = reverse("auth-reset-password")

    def test_reset_password_success(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": "NewPass1234!",
            "new_password_confirm": "NewPass1234!",
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass1234!"))

    def test_reset_password_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        payload = {
            "uid": uid,
            "token": "invalid-token",
            "new_password": "NewPass1234!",
            "new_password_confirm": "NewPass1234!",
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)


class UserMeAPITests(APITestCase):
    def setUp(self):
        self.user = make_user(username="meuser")
        self.url = reverse("users-me")

    def test_patch_can_update_cover_image(self):
        self.client.force_authenticate(user=self.user)
        cover_file = SimpleUploadedFile(
            "cover.jpg",
            b"cover-image-bytes",
            content_type="image/jpeg",
        )

        with patch("user.serializers.default_storage.save") as mock_save, patch(
            "user.serializers.default_storage.url"
        ) as mock_url:
            mock_save.return_value = "users/1/cover/cover.jpg"
            mock_url.return_value = "http://localhost/media/users/1/cover/cover.jpg"

            response = self.client.patch(
                self.url,
                {"cover_image": cover_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cover_image, "http://localhost/media/users/1/cover/cover.jpg")
        self.assertIn("cover_image_url", response.data)
        self.assertEqual(response.data["cover_image_url"], self.user.cover_image)


class PhotographerPublicAPITests(APITestCase):
    def setUp(self):
        self.url = "/api/photographers/"
        self.hanoi = Location.objects.create(city_province="Ha Noi", district="Hoan Kiem")
        self.hcmc = Location.objects.create(city_province="TP. Ho Chi Minh", district="District 1")
        self.customer = make_user(username="customer-api", role=User.Roles.CUSTOMER)
        self.photographer = self._make_photographer(
            username="linh-photo",
            first_name="Linh",
            last_name="Tran",
            bio="Fine art portrait photographer",
            specialties="portrait,wedding",
            experience_years=4,
            gender="female",
            languages=["vi", "en"],
            working_models=["outdoor"],
            working_packages=["PERSONAL", "WEDDING"],
            locations=[self.hanoi],
            rating_avg=Decimal("4.80"),
            total_reviews=5,
        )
        self._make_portfolio(self.photographer, "portfolios/linh/one.jpg")
        self._make_portfolio(self.photographer, "portfolios/linh/two.jpg")
        self.completed_booking = self._make_booking(
            photographer=self.photographer.user,
            location=self.hanoi,
            status=Booking.Status.COMPLETED,
        )
        self.customer_profile = self._make_photographer(
            username="hidden-customer-role",
            role=User.Roles.CUSTOMER,
            bio="This profile should not appear because user is not a photographer.",
        )

    def _make_photographer(self, username, role=User.Roles.PHOTOGRAPHER, locations=None, **profile_attrs):
        user = make_user(username=username, role=role)
        user.first_name = profile_attrs.pop("first_name", "")
        user.last_name = profile_attrs.pop("last_name", "")
        user.avatar = f"https://cdn.example.com/{username}/avatar.jpg"
        user.save(update_fields=["first_name", "last_name", "avatar"])

        profile, _ = PhotographerProfile.objects.get_or_create(user=user)
        for field, value in profile_attrs.items():
            setattr(profile, field, value)
        profile.save()
        if locations is not None:
            profile.active_locations.set(locations)
        return profile

    @staticmethod
    def _make_portfolio(profile, image):
        return Portfolio.objects.create(
            photographer=profile,
            image=image,
            category=Portfolio.Categories.PERSONAL,
        )

    def _make_booking(self, photographer, location, status=Booking.Status.OPEN):
        return Booking.objects.create(
            customer=self.customer,
            photographer=photographer,
            title="Completed portrait session",
            category=Booking.Categories.PERSONAL,
            shoot_date=timezone.localdate() + timedelta(days=10),
            deadline_date=timezone.now() + timedelta(days=5),
            location=location,
            environment=Booking.Environments.OUTDOOR,
            requires_makeup=False,
            budget_min=Decimal("100000.00"),
            budget_max=Decimal("500000.00"),
            status=status,
        )

    def test_public_list_returns_photographer_cards_with_stats(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["id"], self.photographer.id)
        self.assertEqual(item["display_name"], "Linh Tran")
        self.assertEqual(item["avatar_url"], self.photographer.user.avatar)
        self.assertEqual(item["rating_avg"], "4.80")
        self.assertEqual(item["total_reviews"], 5)
        self.assertEqual(item["shooting_count"], 1)
        self.assertEqual(item["favorite_count"], 0)
        self.assertFalse(item["favored"])
        self.assertEqual(len(item["gallery_preview"]), 2)
        self.assertEqual(item["active_locations"][0]["city_province"], "Ha Noi")

    def test_keyword_searches_name_username_bio_and_specialties(self):
        response = self.client.get(self.url, {"keyword": "wedding"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.photographer.id)

        empty_response = self.client.get(self.url, {"keyword": "commercial"})
        self.assertEqual(empty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(empty_response.data["count"], 0)

    def test_advanced_filters_match_profile_metadata(self):
        response = self.client.get(
            self.url,
            {
                "shooting_location": str(self.hanoi.id),
                "experience_in_year": "3_5",
                "gender": "female",
                "languages": "en",
                "work_model": "outdoor",
                "work_packages": "WEDDING",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.photographer.id)

        empty_response = self.client.get(self.url, {"languages": "ja"})
        self.assertEqual(empty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(empty_response.data["count"], 0)

    def test_sorting_and_pagination_are_stable(self):
        popular = self._make_photographer(
            username="popular-photo",
            first_name="Popular",
            experience_years=7,
            rating_avg=Decimal("5.00"),
            total_reviews=8,
            locations=[self.hcmc],
        )
        for index in range(2):
            self._make_booking(
                photographer=popular.user,
                location=self.hcmc,
                status=Booking.Status.COMPLETED,
            )

        response = self.client.get(
            self.url,
            {"sortBy": "shooting_count", "direction": "desc", "page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(response.data["results"][0]["id"], popular.id)

    def test_customer_can_favorite_and_unfavorite_once(self):
        self.client.force_authenticate(user=self.customer)

        create_response = self.client.post(f"{self.url}{self.photographer.id}/favorite/")
        duplicate_response = self.client.post(f"{self.url}{self.photographer.id}/favorite/")
        list_response = self.client.get(self.url)
        delete_response = self.client.delete(f"{self.url}{self.photographer.id}/favorite/")

        self.assertEqual(create_response.status_code, status.HTTP_200_OK)
        self.assertTrue(create_response.data["favored"])
        self.assertEqual(create_response.data["favorite_count"], 1)
        self.assertEqual(duplicate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate_response.data["favorite_count"], 1)
        self.assertTrue(list_response.data["results"][0]["favored"])
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(delete_response.data["favored"])
        self.assertEqual(delete_response.data["favorite_count"], 0)

    def test_favorite_requires_customer_account(self):
        anonymous_response = self.client.post(f"{self.url}{self.photographer.id}/favorite/")
        photographer_user = make_user(username="blocked-photo", role=User.Roles.PHOTOGRAPHER)
        self.client.force_authenticate(user=photographer_user)
        photographer_response = self.client.post(f"{self.url}{self.photographer.id}/favorite/")

        self.assertEqual(anonymous_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(photographer_response.status_code, status.HTTP_403_FORBIDDEN)


class PhotographerProfileMetadataAPITests(APITestCase):
    def setUp(self):
        self.user = make_user(username="profile-meta", role=User.Roles.PHOTOGRAPHER)
        self.url = reverse("photographers-me-profile")

    def test_photographer_can_update_filter_metadata(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "gender": "male",
            "languages": ["vi", "en"],
            "working_models": ["studio", "outdoor"],
            "working_packages": ["PERSONAL", "EVENT"],
        }

        response = self.client.patch(self.url, payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gender"], "male")
        self.assertEqual(response.data["languages"], ["vi", "en"])
        self.assertEqual(response.data["working_models"], ["studio", "outdoor"])
        self.assertEqual(response.data["working_packages"], ["PERSONAL", "EVENT"])


# ---------------------------------------------------------------------------
# Email Service Tests
# ---------------------------------------------------------------------------

class EmailServiceValidationTests(TestCase):
    """Test email configuration validation."""

    def test_validate_email_config_success(self):
        """Test that valid email config passes validation."""
        try:
            EmailService.validate_email_config()
        except ImproperlyConfigured:
            self.fail("Valid email config should not raise ImproperlyConfigured")

    @override_settings(
        EMAIL_HOST="",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="pass",
    )
    def test_validate_email_config_missing_host(self):
        """Test that missing EMAIL_HOST raises ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured) as cm:
            EmailService.validate_email_config()
        self.assertIn("EMAIL_HOST", str(cm.exception))

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="pass",
    )
    def test_validate_email_config_missing_user(self):
        """Test that missing EMAIL_HOST_USER raises ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured) as cm:
            EmailService.validate_email_config()
        self.assertIn("EMAIL_HOST_USER", str(cm.exception))

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="",
    )
    def test_validate_email_config_missing_password(self):
        """Test that missing EMAIL_HOST_PASSWORD raises ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured) as cm:
            EmailService.validate_email_config()
        self.assertIn("EMAIL_HOST_PASSWORD", str(cm.exception))


class EmailServiceSendTests(TestCase):
    """Test email sending functionality."""

    def test_send_email_success(self):
        """Test sending email with text and HTML."""
        result = EmailService.send_email(
            subject="Test Subject",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            text_body="Test text body",
            html_body="<p>Test HTML body</p>",
        )

        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Test Subject")
        self.assertEqual(mail.outbox[0].body, "Test text body")
        self.assertIn("recipient@example.com", mail.outbox[0].to)

    def test_send_email_text_only(self):
        """Test sending email with only text body."""
        result = EmailService.send_email(
            subject="Text Only",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            text_body="Text only body",
        )

        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)
        # Check that no alternatives are attached
        self.assertEqual(len(mail.outbox[0].alternatives), 0)

    def test_send_email_multiple_recipients(self):
        """Test sending email to multiple recipients."""
        recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]
        result = EmailService.send_email(
            subject="Batch Email",
            from_email="sender@example.com",
            to_emails=recipients,
            text_body="Message to all",
        )

        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, recipients)

    @override_settings(EMAIL_HOST="")
    def test_send_email_with_invalid_config_and_fail_silently_true(self):
        """Test that invalid config with fail_silently=True returns 0."""
        result = EmailService.send_email(
            subject="Test",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            text_body="Test",
            fail_silently=True,
        )

        self.assertEqual(result, 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_HOST="")
    def test_send_email_with_invalid_config_and_fail_silently_false(self):
        """Test that invalid config with fail_silently=False raises exception."""
        with self.assertRaises(ImproperlyConfigured):
            EmailService.send_email(
                subject="Test",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                text_body="Test",
                fail_silently=False,
            )


class EmailServicePasswordResetTests(TestCase):
    """Test password reset email functionality."""

    def setUp(self):
        self.user = make_user(username="emailtest")

    def test_send_password_reset_email_success(self):
        """Test sending password reset email."""
        reset_link = "http://localhost:3000/reset-password?uid=123&token=abc"

        result = EmailService.send_password_reset_email(
            user=self.user,
            reset_link=reset_link,
        )

        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Yeu cau dat lai mat khau", mail.outbox[0].subject)
        self.assertIn(reset_link, mail.outbox[0].body)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_send_password_reset_email_contains_html(self):
        """Test that password reset email contains HTML alternative."""
        reset_link = "http://localhost:3000/reset-password?uid=123&token=abc"

        EmailService.send_password_reset_email(
            user=self.user,
            reset_link=reset_link,
        )

        email = mail.outbox[0]
        # Check that HTML alternative is attached
        self.assertGreater(len(email.alternatives), 0)
        html_alternative = email.alternatives[0]
        self.assertEqual(html_alternative[1], "text/html")
        self.assertIn(reset_link, html_alternative[0])

    def test_send_password_reset_email_with_full_name(self):
        """Test password reset email includes user full name when available."""
        self.user.first_name = "John"
        self.user.last_name = "Doe"
        self.user.save()

        reset_link = "http://localhost:3000/reset-password?uid=123&token=abc"

        EmailService.send_password_reset_email(
            user=self.user,
            reset_link=reset_link,
        )

        email = mail.outbox[0]
        self.assertIn("John Doe", email.body)

    def test_send_password_reset_email_fallback_to_username(self):
        """Test password reset email uses username when full name unavailable."""
        reset_link = "http://localhost:3000/reset-password?uid=123&token=abc"

        EmailService.send_password_reset_email(
            user=self.user,
            reset_link=reset_link,
        )

        email = mail.outbox[0]
        self.assertIn(self.user.username, email.body)


class EmailServiceLoggingTests(TestCase):
    """Test email service logging."""

    def setUp(self):
        self.user = make_user(username="loggingtest")

    @patch("user.email_service.logger")
    def test_send_email_logs_on_success(self, mock_logger):
        """Test that successful email sending is logged."""
        EmailService.send_email(
            subject="Test",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            text_body="Test body",
        )

        # Should log info about sending
        self.assertGreaterEqual(mock_logger.info.call_count, 2)

    @patch("user.email_service.logger")
    def test_send_email_logs_on_validation_error(self, mock_logger):
        """Test that validation errors are logged."""
        with patch("user.email_service.EmailService.validate_email_config") as mock_validate:
            mock_validate.side_effect = ImproperlyConfigured("Test error")

            EmailService.send_email(
                subject="Test",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                text_body="Test body",
                fail_silently=True,
            )

        # Should log error
        mock_logger.error.assert_called()
