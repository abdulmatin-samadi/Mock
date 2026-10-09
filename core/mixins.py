"""Access-control mixins/decorators for server-rendered (template) views."""
from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def _check(user, role):
    if role == "admin":
        return user.is_admin
    if role == "student":
        return user.is_student
    raise ValueError(role)


def role_required(*roles):
    """Allow the view if the user has ANY of the given roles. 403 otherwise."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not any(_check(request.user, r) for r in roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required("admin")
student_required = role_required("student")


class RoleRequiredMixin(LoginRequiredMixin):
    roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not any(_check(request.user, r) for r in self.roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    roles = ("admin",)
