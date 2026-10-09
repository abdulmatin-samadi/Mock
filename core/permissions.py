"""Role-based and object-level permission classes for the REST API."""
from rest_framework.permissions import BasePermission


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_admin)


def is_student(user):
    return bool(user and user.is_authenticated and user.is_student)


class IsAdminRole(BasePermission):
    message = "Admin access required."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsStudent(BasePermission):
    message = "Only student accounts can do this."

    def has_permission(self, request, view):
        return is_student(request.user)


class IsOwnerOrAdmin(BasePermission):
    """Object has a `student` FK; only the owner or an admin may access it."""

    owner_field = "student"

    def has_object_permission(self, request, view, obj):
        if is_admin(request.user):
            return True
        owner_id = getattr(obj, f"{getattr(view, 'owner_field', self.owner_field)}_id", None)
        return owner_id == request.user.id
