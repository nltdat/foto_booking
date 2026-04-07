from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PhotographerProfile, user_avatar_upload_path

User = get_user_model()


def _upload_user_avatar(user, avatar_file):
    saved_name = default_storage.save(
        user_avatar_upload_path(user, avatar_file.name),
        avatar_file,
    )
    return default_storage.url(saved_name)


def _to_public_media_url(url):
    if not url:
        return None

    internal = settings.AWS_S3_ENDPOINT_URL.rstrip("/")
    public = settings.AWS_S3_PUBLIC_ENDPOINT_URL.rstrip("/")

    if url.startswith(internal):
        return f"{public}{url[len(internal):]}"
    return url


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()


class UserProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    photographer_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "avatar_url",
            "photographer_profile_id",
        ]

    def get_avatar_url(self, obj):
        if obj.avatar:
            return _to_public_media_url(obj.avatar)

        if not obj.avatar:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.avatar.url)
        return obj.avatar.url

    @staticmethod
    def get_photographer_profile_id(obj):
        profile = getattr(obj, "photographer_profile", None)
        return profile.id if profile else None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "role",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Password confirmation does not match."}
            )
        return attrs

    @staticmethod
    def validate_role(value):
        if value == User.Roles.ADMIN:
            raise serializers.ValidationError(
                "Không thể đăng ký tài khoản ADMIN từ endpoint public."
            )
        return value

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")

        with transaction.atomic():
            user = User(**validated_data)
            user.set_password(password)
            user.save()

            if user.role == User.Roles.PHOTOGRAPHER:
                PhotographerProfile.objects.get_or_create(user=user)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("Email hoặc mật khẩu không đúng.") from exc

        if not user.check_password(password):
            raise AuthenticationFailed("Email hoặc mật khẩu không đúng.")

        if not user.is_active:
            raise AuthenticationFailed("Tài khoản đã bị vô hiệu hóa.")

        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        refresh_token = self.validated_data["refresh"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as exc:
            raise serializers.ValidationError(
                {"refresh": "Refresh token không hợp lệ hoặc đã hết hạn."}
            ) from exc


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserProfileSerializer()


class LogoutResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class UserMeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "avatar"]

    def update(self, instance, validated_data):
        avatar = validated_data.pop("avatar", serializers.empty)
        user = super().update(instance, validated_data)

        if avatar is not serializers.empty:
            if avatar is None:
                user.avatar = ""
            else:
                user.avatar = _upload_user_avatar(user, avatar)
            user.save(update_fields=["avatar"])

        return user


class PhotographerProfileSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = PhotographerProfile
        fields = [
            "id",
            "user",
            "bio",
            "specialties",
            "city",
            "hourly_rate",
            "experience_years",
            "created_at",
            "updated_at",
        ]


class PhotographerProfileUpdateSerializer(serializers.ModelSerializer):
    avatar = serializers.FileField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = PhotographerProfile
        fields = [
            "bio",
            "specialties",
            "city",
            "hourly_rate",
            "experience_years",
            "avatar",
        ]

    def update(self, instance, validated_data):
        has_avatar = "avatar" in validated_data
        avatar = validated_data.pop("avatar", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if has_avatar:
            if avatar is None:
                instance.user.avatar = ""
            else:
                instance.user.avatar = _upload_user_avatar(instance.user, avatar)
            instance.user.save(update_fields=["avatar"])

        return instance
