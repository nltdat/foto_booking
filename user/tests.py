from unittest.mock import MagicMock

from django.test import TestCase

from .models import User
from .permissions import IsPhotographer


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