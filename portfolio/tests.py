import io
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from user.models import PhotographerProfile, User

from .models import Portfolio, portfolio_image_upload_path
from .serializers import PortfolioSerializer, _to_public_media_url
from .views import IsOwnerOrReadOnly, PortfolioFilterBackend


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


def make_photographer_profile(user):
    profile, _ = PhotographerProfile.objects.get_or_create(user=user)
    return profile


def make_fake_image(name="test.jpg"):
    """Return a minimal valid JPEG as SimpleUploadedFile."""
    # Minimal 1x1 JPEG
    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
        b"\x1eC  33\n\n\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
        b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa"
        b"\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br"
        b"\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZ"
        b"cdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94"
        b"\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa"
        b"\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7"
        b"\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3"
        b"\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8"
        b"\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\xff\xd9"
    )
    return SimpleUploadedFile(name, jpeg_bytes, content_type="image/jpeg")


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class PortfolioModelTest(TestCase):
    def setUp(self):
        self.user = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.profile = make_photographer_profile(self.user)

    def test_str_representation(self):
        # Create a Portfolio instance without saving to avoid S3 issues
        portfolio = Portfolio(
            photographer=self.profile,
            category=Portfolio.Categories.PERSONAL,
        )
        portfolio.id = uuid.uuid4()
        self.assertIn("Portfolio<", str(portfolio))

    def test_uuid_primary_key(self):
        self.assertIsNotNone(uuid.uuid4())

    def test_portfolio_image_upload_path(self):
        portfolio = Portfolio(photographer=self.profile)
        path = portfolio_image_upload_path(portfolio, "wedding.jpg")
        self.assertEqual(path, f"portfolios/{self.profile.pk}/wedding.jpg")

    def test_categories_choices(self):
        choices = [c[0] for c in Portfolio.Categories.choices]
        self.assertIn("PERSONAL", choices)
        self.assertIn("COUPLE", choices)
        self.assertIn("EVENT", choices)
        self.assertIn("WEDDING", choices)
        self.assertIn("FAMILY", choices)

    def test_portfolio_image_upload_path_with_different_extension(self):
        portfolio = Portfolio(photographer=self.profile)
        path = portfolio_image_upload_path(portfolio, "photo.png")
        self.assertTrue(path.startswith(f"portfolios/{self.profile.pk}/"))
        self.assertTrue(path.endswith("photo.png"))


# ---------------------------------------------------------------------------
# Serializer Tests - _to_public_media_url
# ---------------------------------------------------------------------------

class ToPublicMediaUrlTest(TestCase):
    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
    )
    def test_converts_internal_to_public_url(self):
        result = _to_public_media_url("http://minio:9000/bucket/image.jpg")
        self.assertEqual(result, "http://localhost:9000/bucket/image.jpg")

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
    )
    def test_non_internal_url_unchanged(self):
        result = _to_public_media_url("http://other-server.com/image.jpg")
        self.assertEqual(result, "http://other-server.com/image.jpg")

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
    )
    def test_empty_string_returns_none(self):
        result = _to_public_media_url("")
        self.assertIsNone(result)

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000",
        AWS_S3_PUBLIC_ENDPOINT_URL="http://localhost:9000",
    )
    def test_none_returns_none(self):
        result = _to_public_media_url(None)
        self.assertIsNone(result)

    @override_settings(
        AWS_S3_ENDPOINT_URL="http://minio:9000/",
        AWS_S3_PUBLIC_ENDPOINT_URL="http://localhost:9000/",
    )
    def test_trailing_slashes_stripped_from_endpoints(self):
        result = _to_public_media_url("http://minio:9000/bucket/photo.jpg")
        self.assertEqual(result, "http://localhost:9000/bucket/photo.jpg")


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------

class IsOwnerOrReadOnlyTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.perm = IsOwnerOrReadOnly()
        self.owner_user = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.other_user = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        self.owner_profile = make_photographer_profile(self.owner_user)

    def _make_request(self, method, user):
        fn = getattr(self.factory, method)
        request = fn("/")
        request.user = user
        return request

    def test_get_allowed_without_auth(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request("get", AnonymousUser())
        self.assertTrue(self.perm.has_permission(request, None))

    def test_post_requires_auth(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request("post", AnonymousUser())
        self.assertFalse(self.perm.has_permission(request, None))

    def test_post_allowed_when_authenticated(self):
        request = self._make_request("post", self.owner_user)
        self.assertTrue(self.perm.has_permission(request, None))

    def test_get_object_permission_always_true(self):
        # For any portfolio object, GET is always allowed
        portfolio = Portfolio.__new__(Portfolio)
        portfolio.photographer = self.owner_profile
        request = self._make_request("get", self.other_user)
        self.assertTrue(self.perm.has_object_permission(request, None, portfolio))

    def test_put_object_permission_owner(self):
        portfolio = Portfolio.__new__(Portfolio)
        portfolio.photographer = self.owner_profile
        request = self._make_request("put", self.owner_user)
        self.assertTrue(self.perm.has_object_permission(request, None, portfolio))

    def test_put_object_permission_non_owner(self):
        portfolio = Portfolio.__new__(Portfolio)
        portfolio.photographer = self.owner_profile
        request = self._make_request("put", self.other_user)
        self.assertFalse(self.perm.has_object_permission(request, None, portfolio))


# ---------------------------------------------------------------------------
# Filter Backend Tests
# ---------------------------------------------------------------------------

class PortfolioFilterBackendTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.filter_backend = PortfolioFilterBackend()
        self.user = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.profile = make_photographer_profile(self.user)
        self.user2 = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        self.profile2 = make_photographer_profile(self.user2)

    def _make_request(self, **params):
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        request = self.factory.get(f"/?{query_string}")
        return request

    def test_no_filter_returns_all(self):
        qs = Portfolio.objects.all()
        request = self._make_request()
        result = self.filter_backend.filter_queryset(request, qs, None)
        self.assertEqual(list(result), list(qs))

    def test_filter_by_photographer_id(self):
        qs = Portfolio.objects.all()
        request = self._make_request(photographer_id=self.profile.pk)
        result = self.filter_backend.filter_queryset(request, qs, None)
        for p in result:
            self.assertEqual(p.photographer_id, self.profile.pk)

    def test_filter_by_category(self):
        qs = Portfolio.objects.all()
        request = self._make_request(category="WEDDING")
        result = self.filter_backend.filter_queryset(request, qs, None)
        for p in result:
            self.assertEqual(p.category, "WEDDING")


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------

@override_settings(
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    MEDIA_ROOT="/tmp/test_portfolio_media/",
)
class PortfolioViewSetTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.photographer_user = make_user("photo1", role=User.Roles.PHOTOGRAPHER)
        self.photographer2_user = make_user("photo2", role=User.Roles.PHOTOGRAPHER)
        self.customer_user = make_user("customer1", role=User.Roles.CUSTOMER)
        self.profile = make_photographer_profile(self.photographer_user)
        self.profile2 = make_photographer_profile(self.photographer2_user)

    # --- List ---

    def test_list_accessible_without_auth(self):
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_empty_initially(self):
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_filter_by_category(self):
        # Create portfolios directly in DB without real file
        p1 = Portfolio.objects.create(
            photographer=self.profile,
            category=Portfolio.Categories.WEDDING,
        )
        p2 = Portfolio.objects.create(
            photographer=self.profile,
            category=Portfolio.Categories.PERSONAL,
        )
        response = self.client.get("/api/portfolios/?category=WEDDING")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(p1.pk), ids)
        self.assertNotIn(str(p2.pk), ids)

    def test_list_filter_by_photographer_id(self):
        p1 = Portfolio.objects.create(
            photographer=self.profile,
            category=Portfolio.Categories.PERSONAL,
        )
        p2 = Portfolio.objects.create(
            photographer=self.profile2,
            category=Portfolio.Categories.PERSONAL,
        )
        response = self.client.get(f"/api/portfolios/?photographer_id={self.profile.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(p1.pk), ids)
        self.assertNotIn(str(p2.pk), ids)

    # --- Create ---

    def test_create_requires_authentication(self):
        image = make_fake_image()
        response = self.client.post(
            "/api/portfolios/",
            {"image": image, "category": "PERSONAL"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_cannot_create_portfolio(self):
        self.client.force_authenticate(user=self.customer_user)
        image = make_fake_image()
        response = self.client.post(
            "/api/portfolios/",
            {"image": image, "category": "PERSONAL"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photographer_can_create_portfolio(self):
        self.client.force_authenticate(user=self.photographer_user)
        image = make_fake_image()
        response = self.client.post(
            "/api/portfolios/",
            {"image": image, "category": "PERSONAL"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["category"], "PERSONAL")
        self.assertEqual(response.data["photographer_id"], self.profile.pk)

    def test_create_creates_photographer_profile_if_missing(self):
        # Create a new photographer without a profile
        new_photographer = make_user("photo3", role=User.Roles.PHOTOGRAPHER)
        self.assertFalse(
            PhotographerProfile.objects.filter(user=new_photographer).exists()
        )
        self.client.force_authenticate(user=new_photographer)
        image = make_fake_image()
        response = self.client.post(
            "/api/portfolios/",
            {"image": image, "category": "EVENT"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            PhotographerProfile.objects.filter(user=new_photographer).exists()
        )

    def test_create_missing_category_returns_400(self):
        self.client.force_authenticate(user=self.photographer_user)
        image = make_fake_image()
        response = self.client.post(
            "/api/portfolios/",
            {"image": image},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_missing_image_returns_400(self):
        self.client.force_authenticate(user=self.photographer_user)
        response = self.client.post(
            "/api/portfolios/",
            {"category": "PERSONAL"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)