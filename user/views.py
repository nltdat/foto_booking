import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .email_service import EmailService
from .models import PhotographerProfile, User
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


class PhotographerMeProfileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPhotographer]
    parser_classes = [MultiPartParser, FormParser]

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
        request={"multipart/form-data": PhotographerProfileUpdateSerializer},
        responses={200: PhotographerProfileSerializer},
    )
    def patch(self, request, *args, **kwargs):
        content_type = (request.content_type or "").lower()
        if not content_type.startswith("multipart/form-data"):
            return Response(
                {"detail": "Vui long gui du lieu bang multipart/form-data."},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

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
