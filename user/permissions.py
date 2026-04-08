from rest_framework import permissions

from .models import User


class IsPhotographer(permissions.BasePermission):
    message = "Chi nhiep anh gia moi co quyen truy cap tai nguyen nay."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Roles.PHOTOGRAPHER
        )
