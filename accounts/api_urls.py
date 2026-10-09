from django.urls import path
from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("users", api_views.UserViewSet, basename="user")

urlpatterns = [
    path("auth/register/", api_views.RegisterAPIView.as_view(), name="api-register"),
    path("auth/login/", api_views.LoginAPIView.as_view(), name="api-login"),
    path("auth/token/refresh/", api_views.RefreshAPIView.as_view(), name="api-token-refresh"),
    path("auth/logout/", api_views.LogoutAPIView.as_view(), name="api-logout"),
    path("auth/password/change/", api_views.ChangePasswordAPIView.as_view(), name="api-password-change"),
    path("auth/password/reset/", api_views.PasswordResetAPIView.as_view(), name="api-password-reset"),
    path("auth/password/reset/confirm/", api_views.PasswordResetConfirmAPIView.as_view(),
         name="api-password-reset-confirm"),
] + router.urls
