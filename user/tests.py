from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .models import User
from .permissions import IsPhotographer


class IsPhotographerPermissionTest(TestCase):
    """Tests for the user.permissions.IsPhotographer permission class."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsPhotographer()
        self.photographer = User.objects.create_user(
            username="photo1",
            email="photo1@test.com",
            password="pass123",
            role=User.Roles.PHOTOGRAPHER,
        )
        self.customer = User.objects.create_user(
            username="customer1",
            email="customer1@test.com",
            password="pass123",
            role=User.Roles.CUSTOMER,
        )
        self.admin = User.objects.create_user(
            username="admin1",
            email="admin1@test.com",
            password="pass123",
            role=User.Roles.ADMIN,
        )

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

    def test_admin_denied(self):
        request = self._make_request(self.admin)
        self.assertFalse(self.perm.has_permission(request, None))

    def test_unauthenticated_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(AnonymousUser())
        self.assertFalse(self.perm.has_permission(request, None))

    def test_permission_message_set(self):
        self.assertIsNotNone(self.perm.message)
        self.assertGreater(len(self.perm.message), 0)