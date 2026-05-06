import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from bookings.models import Booking
from .email_service import EmailService
from .models import PhotographerFavorite, PhotographerProfile, User
from .permissions import IsPhotographer
from .serializers import (
    DeleteAccountResponseSerializer,
    DeleteAccountSerializer,
    ForgotPasswordResponseSerializer,
    ForgotPasswordSerializer,
    HealthCheckSerializer,
    LoginSerializer,
    LogoutResponseSerializer,
    LogoutSerializer,
    PhotographerFavoriteStateSerializer,
    PhotographerListSerializer,
    PhotographerProfileSerializer,
    PhotographerProfileUpdateSerializer,
    RegisterSerializer,
    ResetPasswordResponseSerializer,
    ResetPasswordSerializer,
    TokenPairResponseSerializer,
    UserMeUpdateSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_array_contains_any(queryset, field_name, values):
    values = [value for value in values if value]
    if not values:
        return queryset

    query = Q()
    for value in values:
        query |= Q(**{f"{field_name}__contains": [value]})
    return queryset.filter(query)


class PhotographerPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 48


class HealthCheckAPIView(APIView):
    @extend_schema(
        summary="Health check",
        description="Example endpoint to demonstrate serializer-based schema generation.",
        responses={200: HealthCheckSerializer},
    )
    def get(self, request, *args, **kwargs):
        serializer = HealthCheckSerializer(
            {
                "status": "ok",
                "service": "fotonow-backend",
            }
        )
        return Response(serializer.data)


class RegisterAPIView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    @extend_schema(
        tags=["Authentication"],
        summary="Đăng ký tài khoản",
        description=(
            "Đăng ký user mới với role CUSTOMER hoặc PHOTOGRAPHER. "
            "Nếu role là PHOTOGRAPHER hệ thống sẽ tự tạo PhotographerProfile."
        ),
        request=RegisterSerializer,
        responses={201: UserProfileSerializer},
    )
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        output = UserProfileSerializer(user, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Đăng nhập lấy JWT",
        request=LoginSerializer,
        responses={200: TokenPairResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserProfileSerializer(user, context={"request": request}).data,
        }
        return Response(data, status=status.HTTP_200_OK)


class LogoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Authentication"],
        summary="Đăng xuất",
        description="Đăng xuất bằng cách đưa refresh token vào blacklist.",
        request=LogoutSerializer,
        responses={200: LogoutResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Đăng xuất thành công."},
            status=status.HTTP_200_OK,
        )


class ForgotPasswordAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Quên mật khẩu",
        request=ForgotPasswordSerializer,
        responses={200: ForgotPasswordResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = f"{settings.FRONTEND_RESET_PASSWORD_URL}?uid={uid}&token={token}"
            EmailService.send_password_reset_email(
                user=user,
                reset_link=reset_link,
                fail_silently=True,
            )
        else:
            logger.info("Password reset requested for unknown email: %s", email)

        return Response(
            {"detail": "Nếu email tồn tại, hướng dẫn đặt lại mật khẩu sẽ được gửi."},
            status=status.HTTP_200_OK,
        )


class ResetPasswordAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Đặt lại mật khẩu",
        request=ResetPasswordSerializer,
        responses={200: ResetPasswordResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Đặt lại mật khẩu thành công."},
            status=status.HTTP_200_OK,
        )


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        tags=["Users"],
        summary="Lấy thông tin cá nhân",
        responses={200: UserProfileSerializer},
    )
    def get(self, request, *args, **kwargs):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Users"],
        summary="Cập nhật thông tin cá nhân",
        description=(
            "Hỗ trợ upload avatar qua multipart/form-data để lưu trực tiếp vào "
            "MinIO thông qua django-storages. Có thể gửi thêm cover_image để "
            "cập nhật ảnh bìa."
        ),
        request={
            "application/json": UserMeUpdateSerializer,
            "multipart/form-data": UserMeUpdateSerializer,
        },
        responses={200: UserProfileSerializer},
    )
    def patch(self, request, *args, **kwargs):
        serializer = UserMeUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        output = UserProfileSerializer(request.user, context={"request": request})
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Users"],
        summary="Xóa tài khoản",
        description=(
            "Xóa tài khoản người dùng hiện tại. Yêu cầu xác nhận bằng mật khẩu. "
            "Thao tác này không thể hoàn tác."
        ),
        request=DeleteAccountSerializer,
        responses={200: DeleteAccountResponseSerializer},
    )
    def delete(self, request, *args, **kwargs):
        serializer = DeleteAccountSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Tài khoản đã được xóa thành công."},
            status=status.HTTP_200_OK,
        )


class PhotographerListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PhotographerListSerializer
    pagination_class = PhotographerPagination

    def get_queryset(self):
        request = self.request
        queryset = (
            PhotographerProfile.objects.select_related("user")
            .prefetch_related("active_locations", "portfolios")
            .filter(user__role=User.Roles.PHOTOGRAPHER, user__is_active=True)
        )

        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            queryset = queryset.filter(
                Q(user__first_name__icontains=keyword)
                | Q(user__last_name__icontains=keyword)
                | Q(user__username__icontains=keyword)
                | Q(user__email__icontains=keyword)
                | Q(bio__icontains=keyword)
                | Q(specialties__icontains=keyword)
            )

        shooting_location = request.query_params.get("shooting_location", "").strip()
        if shooting_location:
            if shooting_location.isdigit():
                queryset = queryset.filter(active_locations__id=int(shooting_location))
            else:
                queryset = queryset.filter(
                    active_locations__city_province__icontains=shooting_location
                )

        experience = request.query_params.get("experience_in_year", "").strip()
        if experience:
            if experience in {"under_1", "lt1", "0_1"}:
                queryset = queryset.filter(experience_years__lt=1)
            elif experience == "1_3":
                queryset = queryset.filter(experience_years__gte=1, experience_years__lte=3)
            elif experience == "3_5":
                queryset = queryset.filter(experience_years__gte=3, experience_years__lte=5)
            elif experience in {"5_plus", "over_5"}:
                queryset = queryset.filter(experience_years__gte=5)
            elif experience.isdigit():
                queryset = queryset.filter(experience_years=int(experience))

        gender = request.query_params.get("gender", "").strip()
        if gender:
            queryset = queryset.filter(gender=gender)

        queryset = _json_array_contains_any(
            queryset,
            "languages",
            _split_csv(request.query_params.get("languages", "")),
        )
        queryset = _json_array_contains_any(
            queryset,
            "working_models",
            _split_csv(request.query_params.get("work_model", "")),
        )
        queryset = _json_array_contains_any(
            queryset,
            "working_packages",
            _split_csv(request.query_params.get("work_packages", "")),
        )

        user = request.user
        if user.is_authenticated and user.role == User.Roles.CUSTOMER:
            favored = PhotographerFavorite.objects.filter(
                customer=user,
                photographer=OuterRef("pk"),
            )
            queryset = queryset.annotate(favored=Exists(favored))
        else:
            queryset = queryset.annotate(
                favored=Value(False, output_field=BooleanField())
            )

        queryset = queryset.annotate(
            favorite_count=Count("favorites", distinct=True),
            shooting_count=Count(
                "user__bookings_assigned",
                filter=Q(user__bookings_assigned__status=Booking.Status.COMPLETED),
                distinct=True,
            ),
        ).distinct()

        sort_by = request.query_params.get("sortBy", "createdAt")
        direction = request.query_params.get("direction", "desc")
        sort_fields = {
            "createdAt": "created_at",
            "created_at": "created_at",
            "shooting_count": "shooting_count",
            "favorite_count": "favorite_count",
            "rating": "rating_avg",
        }
        sort_field = sort_fields.get(sort_by, "created_at")
        prefix = "" if direction == "asc" else "-"
        return queryset.order_by(f"{prefix}{sort_field}", "id")


class PhotographerFavoriteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_profile(self, profile_id):
        return generics.get_object_or_404(
            PhotographerProfile.objects.filter(user__role=User.Roles.PHOTOGRAPHER),
            pk=profile_id,
        )

    @staticmethod
    def _ensure_customer(user):
        if user.role != User.Roles.CUSTOMER:
            raise PermissionDenied("Chi khach hang moi co the yeu thich nhiep anh gia.")

    @staticmethod
    def _response(profile, favored):
        serializer = PhotographerFavoriteStateSerializer(
            {
                "photographer_id": profile.id,
                "favored": favored,
                "favorite_count": profile.favorites.count(),
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, profile_id, *args, **kwargs):
        self._ensure_customer(request.user)
        profile = self._get_profile(profile_id)
        PhotographerFavorite.objects.get_or_create(
            customer=request.user,
            photographer=profile,
        )
        return self._response(profile, favored=True)

    def delete(self, request, profile_id, *args, **kwargs):
        self._ensure_customer(request.user)
        profile = self._get_profile(profile_id)
        PhotographerFavorite.objects.filter(
            customer=request.user,
            photographer=profile,
        ).delete()
        return self._response(profile, favored=False)


class PhotographerMeProfileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPhotographer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_profile(self):
        profile, _ = PhotographerProfile.objects.get_or_create(user=self.request.user)
        return profile

    @extend_schema(
        tags=["Photographer Profile"],
        summary="Lấy hồ sơ NAG hiện tại",
        responses={200: PhotographerProfileSerializer},
    )
    def get(self, request, *args, **kwargs):
        profile = self._get_profile()
        serializer = PhotographerProfileSerializer(profile, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Photographer Profile"],
        summary="Cập nhật hồ sơ NAG",
        description=(
            "Cập nhật thông tin hồ sơ nhiếp ảnh gia. Nếu gửi avatar bằng "
            "multipart/form-data, ảnh sẽ được lưu vào MinIO."
        ),
        request={
            "application/json": PhotographerProfileUpdateSerializer,
            "multipart/form-data": PhotographerProfileUpdateSerializer,
        },
        responses={200: PhotographerProfileSerializer},
    )
    def patch(self, request, *args, **kwargs):
        profile = self._get_profile()
        serializer = PhotographerProfileUpdateSerializer(
            instance=profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        output = PhotographerProfileSerializer(profile, context={"request": request})
        return Response(output.data, status=status.HTTP_200_OK)
