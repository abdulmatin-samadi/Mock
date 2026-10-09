from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User
from .serializers import (
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import register_user, send_password_reset


class AuthThrottleMixin:
    throttle_scope = "auth"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle()]


class RegisterAPIView(AuthThrottleMixin, APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        user = register_user(
            email=d["email"], password=d["password"], first_name=d["first_name"], last_name=d["last_name"],
        )
        refresh = RefreshToken.for_user(user)
        return Response(
            {"user": UserSerializer(user, context={"request": request}).data,
             "refresh": str(refresh), "access": str(refresh.access_token)},
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(AuthThrottleMixin, TokenObtainPairView):
    """POST {email, password} -> {access, refresh}"""


class RefreshAPIView(TokenRefreshView):
    pass


class LogoutAPIView(APIView):
    """POST {refresh} — blacklists the refresh token."""

    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response({"refresh": "This field is required."}, status=400)
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            return Response({"detail": "Invalid or expired token."}, status=400)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ChangePasswordAPIView(APIView):
    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Password changed."})


class PasswordResetAPIView(AuthThrottleMixin, APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = PasswordResetRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        send_password_reset(request, s.validated_data["email"])
        return Response({"detail": "If an account exists for this email, a reset link has been sent."})


class PasswordResetConfirmAPIView(AuthThrottleMixin, APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.validated_data["user"]
        user.set_password(s.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password has been reset."})


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                  viewsets.GenericViewSet):
    """/api/users/ — a user can only see and edit their own record.
    (Admins manage everyone through /api/admin/users/.)"""

    serializer_class = UserSerializer
    http_method_names = ["get", "patch", "put", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(pk=self.request.user.pk)

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        if request.method == "PATCH":
            s = self.get_serializer(request.user, data=request.data, partial=True)
            s.is_valid(raise_exception=True)
            s.save()
            return Response(s.data)
        return Response(self.get_serializer(request.user).data)
