from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView

from .models import PhotographerProfile, User
from .permissions import IsPhotographer
from .serializers import (
    HealthCheckSerializer,
    LoginSerializer,
    LogoutResponseSerializer,
    LogoutSerializer,
    PhotographerProfileSerializer,
    PhotographerProfileUpdateSerializer,
    RegisterSerializer,
    TokenPairResponseSerializer,
    UserMeUpdateSerializer,
    UserProfileSerializer,
)


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
            "MinIO thông qua django-storages."
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
