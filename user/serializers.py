from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.http import urlsafe_base64_decode
from django.core.files.storage import default_storage
from django.db import transaction
from django.conf import settings
import logging
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    PhotographerProfile,
    user_avatar_upload_path,
    user_cover_image_upload_path,
)

User = get_user_model()


def _upload_user_avatar(user, avatar_file):
    saved_name = default_storage.save(
        user_avatar_upload_path(user, avatar_file.name),
        avatar_file,
    )
    return default_storage.url(saved_name)


def _upload_user_cover_image(user, cover_image_file):
    saved_name = default_storage.save(
        user_cover_image_upload_path(user, cover_image_file.name),
        cover_image_file,
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
    cover_image_url = serializers.SerializerMethodField()
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
            "cover_image_url",
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

    def get_cover_image_url(self, obj):
        if obj.cover_image:
            return _to_public_media_url(obj.cover_image)

        if not obj.cover_image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.cover_image.url)
        return obj.cover_image.url

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


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    default_error_messages = {
        "invalid_reset_link": "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
    }

    def validate(self, attrs):
        logger = logging.getLogger(__name__)
        token = attrs.get("token")
        logger.debug(
            "ResetPasswordSerializer.validate called; keys=%s uid=%s token_present=%s token_len=%s new_password_present=%s",
            list(attrs.keys()),
            attrs.get("uid"),
            bool(token),
            len(token) if token else 0,
            "new_password" in attrs,
        )

        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Password confirmation does not match."}
            )

        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
            logger.warning(
                "ResetPasswordSerializer: failed to decode uid=%s error=%s",
                attrs.get("uid"),
                exc,
            )
            raise serializers.ValidationError(
                {"uid": self.error_messages["invalid_reset_link"]}
            ) from exc

        token_val = attrs.get("token")
        token_len = len(token_val) if token_val else 0
        try:
            masked = f"{token_val[:4]}...{token_val[-4:]}" if token_len > 8 else token_val
        except Exception:
            masked = None

        if not default_token_generator.check_token(user, attrs["token"]):
            logger.warning(
                "ResetPasswordSerializer: token invalid for uid=%s token_mask=%s token_len=%s",
                attrs.get("uid"),
                masked,
                token_len,
            )
            raise serializers.ValidationError(
                {"token": self.error_messages["invalid_reset_link"]}
            )

        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as e:
            logger.warning(
                "ResetPasswordSerializer: password validation failed for uid=%s errors=%s",
                attrs.get("uid"),
                e.messages,
            )
            raise serializers.ValidationError({"new_password": e.messages}) from e

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class ResetPasswordResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class UserMeUpdateSerializer(serializers.ModelSerializer):
    avatar = serializers.FileField(write_only=True, required=False, allow_null=True)
    cover_image = serializers.FileField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "avatar", "cover_image"]

    def update(self, instance, validated_data):
        avatar = validated_data.pop("avatar", serializers.empty)
        cover_image = validated_data.pop("cover_image", serializers.empty)
        user = super().update(instance, validated_data)

        if avatar is not serializers.empty:
            if avatar is None:
                user.avatar = ""
            else:
                user.avatar = _upload_user_avatar(user, avatar)
            user.save(update_fields=["avatar"])

        if cover_image is not serializers.empty:
            if cover_image is None:
                user.cover_image = ""
            else:
                user.cover_image = _upload_user_cover_image(user, cover_image)
            user.save(update_fields=["cover_image"])

        return user


class PhotographerProfileSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    active_locations = serializers.SerializerMethodField()

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
            "active_locations",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def get_active_locations(obj):
        return [
            {
                "id": location.id,
                "city_province": location.city_province,
                "district": location.district,
            }
            for location in obj.active_locations.all()
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


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=1)

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Không tìm thấy người dùng.")

        user = request.user
        password = attrs.get("password", "")

        if not user.check_password(password):
            raise serializers.ValidationError(
                {"password": "Mật khẩu không đúng."}
            )

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.delete()
        return user


class DeleteAccountResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
