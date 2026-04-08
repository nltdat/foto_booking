from rest_framework import permissions

from user.models import User


class IsCustomer(permissions.BasePermission):
    """Allow access only for customer role users."""

    message = "Chi khach hang moi co quyen tao booking."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Roles.CUSTOMER
        )


class IsPhotographer(permissions.BasePermission):
    """Allow access only for photographer role users."""

    message = "Chi nhiep anh gia moi co quyen gui bao gia."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Roles.PHOTOGRAPHER
        )


class IsBookingOwner(permissions.BasePermission):
    """Allow action only if request user owns the booking object."""

    message = "Chi chu booking moi co quyen chap nhan bao gia."

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.customer_id == request.user.id
        )
