from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User
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