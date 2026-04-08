import io
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from user.models import PhotographerProfile, User

from .models import Portfolio, portfolio_image_upload_path
from .serializers import PortfolioSerializer, _to_public_media_url
from .views import IsOwnerOrReadOnly, PortfolioFilterBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def make_profile(user):
    profile, _ = PhotographerProfile.objects.get_or_create(user=user)
    return profile


def make_portfolio(profile, category="PERSONAL"):
    return Portfolio.objects.create(
        photographer=profile,
        image="portfolios/test/photo.jpg",
        category=category,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestPortfolioImageUploadPath(TestCase):
    def test_upload_path_format(self):
        instance = MagicMock()
        instance.photographer_id = 42
        path = portfolio_image_upload_path(instance, "photo.jpg")
        self.assertEqual(path, "portfolios/42/photo.jpg")

    def test_upload_path_preserves_filename(self):
        instance = MagicMock()
        instance.photographer_id = 7
        path = portfolio_image_upload_path(instance, "my_beautiful_shot.png")
        self.assertEqual(path, "portfolios/7/my_beautiful_shot.png")


class TestPortfolioModel(TestCase):
    def setUp(self):
        self.photographer_user = make_photographer()
        self.profile = make_profile(self.photographer_user)

    def test_str_representation(self):
        portfolio = make_portfolio(self.profile)
        self.assertIn("Portfolio<", str(portfolio))

    def test_uuid_primary_key(self):
        portfolio = make_portfolio(self.profile)
        self.assertIsInstance(portfolio.id, uuid.UUID)

    def test_category_choices(self):
        expected = {"PERSONAL", "COUPLE", "EVENT", "WEDDING", "FAMILY"}
        actual = {c[0] for c in Portfolio.Categories.choices}
        self.assertEqual(actual, expected)

    def test_ordering_by_created_at_descending(self):
        p1 = make_portfolio(self.profile, category="PERSONAL")
        p2 = make_portfolio(self.profile, category="COUPLE")
        portfolios = list(Portfolio.objects.all())
        self.assertEqual(portfolios[0].id, p2.id)
        self.assertEqual(portfolios[1].id, p1.id)

    def test_cascade_delete_on_profile_delete(self):
        portfolio = make_portfolio(self.profile)
        portfolio_id = portfolio.id
        self.profile.delete()
        with self.assertRaises(Portfolio.DoesNotExist):
            Portfolio.objects.get(id=portfolio_id)


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestToPublicMediaUrl(TestCase):
    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="https://cdn.example.com",
    )
    def test_replaces_internal_endpoint_with_public(self):
        url = "http://minio:9000/bucket/portfolios/1/photo.jpg"
        result = _to_public_media_url(url)
        self.assertEqual(result, "https://cdn.example.com/bucket/portfolios/1/photo.jpg")

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="https://cdn.example.com",
    )
    def test_returns_unchanged_url_if_not_internal(self):
        url = "https://other.cdn.net/photo.jpg"
        result = _to_public_media_url(url)
        self.assertEqual(result, "https://other.cdn.net/photo.jpg")

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="https://cdn.example.com",
    )
    def test_returns_none_for_empty_url(self):
        result = _to_public_media_url("")
        self.assertIsNone(result)

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="https://cdn.example.com",
    )
    def test_returns_none_for_none_url(self):
        result = _to_public_media_url(None)
        self.assertIsNone(result)

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000/",
        AWS_S3_PUBLIC_ENDPOINT_URL="https://cdn.example.com/",
    )
    def test_strips_trailing_slash_from_endpoints(self):
        url = "http://minio:9000/bucket/photo.jpg"
        result = _to_public_media_url(url)
        self.assertEqual(result, "https://cdn.example.com/bucket/photo.jpg")


class TestPortfolioSerializer(TestCase):
    def setUp(self):
        self.photographer_user = make_photographer()
        self.profile = make_profile(self.photographer_user)

    def test_image_is_write_only(self):
        serializer = PortfolioSerializer()
        self.assertTrue(serializer.fields["image"].write_only)

    def test_read_only_fields(self):
        serializer = PortfolioSerializer()
        for field in ["id", "photographer_id", "image_url", "created_at"]:
            self.assertTrue(
                serializer.fields[field].read_only,
                f"Field {field} should be read-only",
            )

    def test_get_image_url_returns_none_when_no_image(self):
        portfolio = Portfolio(photographer=self.profile, category="PERSONAL")
        portfolio.image = None
        result = PortfolioSerializer.get_image_url(portfolio)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------

class TestIsOwnerOrReadOnly(TestCase):
    def setUp(self):
        self.photographer_user = make_photographer()
        self.profile = make_profile(self.photographer_user)
        self.portfolio = make_portfolio(self.profile)
        self.other_user = make_photographer(username="other_photo")

    def _make_request(self, method, user=None):
        request = MagicMock()
        request.method = method
        request.user = user or MagicMock()
        return request

    def test_safe_methods_allowed_for_all(self):
        perm = IsOwnerOrReadOnly()
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = self._make_request(method)
            self.assertTrue(perm.has_permission(request, None))

    def test_unsafe_methods_require_authentication(self):
        perm = IsOwnerOrReadOnly()
        request = self._make_request("POST")
        request.user.is_authenticated = True
        self.assertTrue(perm.has_permission(request, None))

    def test_unsafe_methods_denied_for_unauthenticated(self):
        perm = IsOwnerOrReadOnly()
        request = self._make_request("POST")
        request.user = None
        self.assertFalse(perm.has_permission(request, None))

    def test_owner_can_modify_portfolio(self):
        perm = IsOwnerOrReadOnly()
        request = self._make_request("DELETE", self.photographer_user)
        self.assertTrue(perm.has_object_permission(request, None, self.portfolio))

    def test_non_owner_cannot_modify_portfolio(self):
        perm = IsOwnerOrReadOnly()
        request = self._make_request("DELETE", self.other_user)
        self.assertFalse(perm.has_object_permission(request, None, self.portfolio))

    def test_safe_method_allowed_on_any_object(self):
        perm = IsOwnerOrReadOnly()
        request = self._make_request("GET", self.other_user)
        self.assertTrue(perm.has_object_permission(request, None, self.portfolio))


# ---------------------------------------------------------------------------
# Filter backend tests
# ---------------------------------------------------------------------------

class TestPortfolioFilterBackend(TestCase):
    def setUp(self):
        self.photographer_user = make_photographer()
        self.profile = make_profile(self.photographer_user)
        other_user = make_photographer(username="photo2")
        self.other_profile = make_profile(other_user)

        self.personal = make_portfolio(self.profile, category="PERSONAL")
        self.wedding = make_portfolio(self.profile, category="WEDDING")
        self.other_personal = make_portfolio(self.other_profile, category="PERSONAL")

    def _make_request(self, **query_params):
        request = MagicMock()
        request.query_params = query_params
        return request

    def test_filter_by_category(self):
        backend = PortfolioFilterBackend()
        request = self._make_request(category="PERSONAL")
        queryset = Portfolio.objects.all()
        filtered = backend.filter_queryset(request, queryset, None)
        ids = list(filtered.values_list("id", flat=True))
        self.assertIn(self.personal.id, ids)
        self.assertIn(self.other_personal.id, ids)
        self.assertNotIn(self.wedding.id, ids)

    def test_filter_by_photographer_id(self):
        backend = PortfolioFilterBackend()
        request = self._make_request(photographer_id=str(self.profile.id))
        queryset = Portfolio.objects.all()
        filtered = backend.filter_queryset(request, queryset, None)
        ids = list(filtered.values_list("id", flat=True))
        self.assertIn(self.personal.id, ids)
        self.assertIn(self.wedding.id, ids)
        self.assertNotIn(self.other_personal.id, ids)

    def test_filter_by_both_category_and_photographer_id(self):
        backend = PortfolioFilterBackend()
        request = self._make_request(
            category="PERSONAL", photographer_id=str(self.profile.id)
        )
        queryset = Portfolio.objects.all()
        filtered = backend.filter_queryset(request, queryset, None)
        ids = list(filtered.values_list("id", flat=True))
        self.assertIn(self.personal.id, ids)
        self.assertNotIn(self.wedding.id, ids)
        self.assertNotIn(self.other_personal.id, ids)

    def test_no_filters_returns_all(self):
        backend = PortfolioFilterBackend()
        request = self._make_request()
        queryset = Portfolio.objects.all()
        filtered = backend.filter_queryset(request, queryset, None)
        self.assertEqual(filtered.count(), 3)


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------

class TestPortfolioViewSet(APITestCase):
    def setUp(self):
        self.photographer_user = make_photographer()
        self.profile = make_profile(self.photographer_user)
        self.customer = make_customer()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_list_portfolios_is_public(self):
        make_portfolio(self.profile)
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_portfolios_anonymous_user(self):
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_filter_by_category(self):
        make_portfolio(self.profile, category="PERSONAL")
        make_portfolio(self.profile, category="WEDDING")

        response = self.client.get("/api/portfolios/?category=PERSONAL")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        categories = [p["category"] for p in response.data["results"]]
        self.assertTrue(all(c == "PERSONAL" for c in categories))

    def test_list_filter_by_photographer_id(self):
        other_user = make_photographer(username="photo2")
        other_profile = make_profile(other_user)
        p1 = make_portfolio(self.profile)
        p2 = make_portfolio(other_profile)

        response = self.client.get(f"/api/portfolios/?photographer_id={self.profile.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in response.data["results"]]
        self.assertIn(str(p1.id), ids)
        self.assertNotIn(str(p2.id), ids)

    def test_customer_cannot_create_portfolio(self):
        self._auth(self.customer)
        data = {
            "category": "PERSONAL",
            "image": io.BytesIO(b"fake-image-content"),
        }
        response = self.client.post("/api/portfolios/", data, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_portfolio(self):
        data = {
            "category": "PERSONAL",
            "image": io.BytesIO(b"fake-image-content"),
        }
        response = self.client.post("/api/portfolios/", data, format="multipart")
        # IsOwnerOrReadOnly allows unauthenticated POSTs at has_permission,
        # but perform_create raises PermissionDenied for non-authenticated users
        # Actually has_permission returns False for unauthenticated non-safe methods
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_photographer_cannot_delete_other_photographer_portfolio(self):
        other_user = make_photographer(username="photo2")
        other_profile = make_profile(other_user)
        portfolio = make_portfolio(other_profile)

        self._auth(self.photographer_user)
        response = self.client.delete(f"/api/portfolios/{portfolio.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photographer_can_delete_own_portfolio(self):
        portfolio = make_portfolio(self.profile)
        self._auth(self.photographer_user)
        response = self.client.delete(f"/api/portfolios/{portfolio.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_retrieve_portfolio_is_public(self):
        portfolio = make_portfolio(self.profile)
        response = self.client.get(f"/api/portfolios/{portfolio.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(portfolio.id))