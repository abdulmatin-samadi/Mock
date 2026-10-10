"""Sign in with Google (OAuth 2.0 authorization-code flow, no extra packages).

Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to show the button. In the Google Cloud console the
authorised redirect URI must be <site>/accounts/google/callback/ (or GOOGLE_REDIRECT_URI if set)."""
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext

from .guest import convert_guest, merge_guest_into
from .models import User

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SESSION_KEY = "google_oauth"


class GoogleError(Exception):
    pass


def enabled():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def redirect_uri(request):
    return settings.GOOGLE_REDIRECT_URI or request.build_absolute_uri(reverse("accounts:google_callback"))


def _http():
    import httpx2  # bundled with the AI SDKs; carries its own CA certificates

    return httpx2.Client(timeout=15)


def fetch_profile(request, code):
    """Exchange the code for a token and return Google's userinfo (email, email_verified, names)."""
    with _http() as client:
        token = client.post(TOKEN_URL, data={
            "code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri(request), "grant_type": "authorization_code"})
        if token.status_code != 200:
            raise GoogleError(f"token exchange failed ({token.status_code}): {token.text[:200]}")
        access = token.json().get("access_token")
        info = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access}"})
        if info.status_code != 200:
            raise GoogleError(f"userinfo failed ({info.status_code})")
        return info.json()


def start(request):
    if not enabled():
        raise Http404
    state = secrets.token_urlsafe(24)
    nxt = request.GET.get("next", "")
    request.session[SESSION_KEY] = {"state": state, "next": nxt}
    params = {"client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri(request), "response_type": "code",
              "scope": "openid email profile", "state": state, "prompt": "select_account"}
    return redirect(f"{AUTH_URL}?{urlencode(params)}")


def callback(request):
    if not enabled():
        raise Http404
    from .views import _safe_next

    saved = request.session.pop(SESSION_KEY, None) or {}
    fail = gettext("Google sign-in did not work. Please try again or use your email and password.")
    if request.GET.get("error") or not saved or not secrets.compare_digest(saved.get("state", ""),
                                                                          request.GET.get("state", "")):
        messages.error(request, fail)
        return redirect("accounts:login")
    try:
        info = fetch_profile(request, request.GET.get("code", ""))
    except Exception as e:  # network problems, bad code, Google errors
        logger.warning("Google sign-in failed: %s", e)
        messages.error(request, fail)
        return redirect("accounts:login")
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        messages.error(request, gettext("Your Google account has no verified email address."))
        return redirect("accounts:login")

    guest = request.user if request.user.is_authenticated and request.user.is_guest else None
    first = (info.get("given_name") or email.split("@")[0])[:150]
    last = (info.get("family_name") or "")[:150]
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        if guest:  # keep the free mock the visitor already took
            user = convert_guest(guest, email=email, password=None, first_name=first, last_name=last)
        else:
            user = User.objects.create_user(email=email, password=None, first_name=first, last_name=last)
        messages.success(request, gettext("Welcome, %(name)s! All mocks are now open.") % {"name": user.first_name})
    elif not user.is_active:
        messages.error(request, gettext("This account is disabled."))
        return redirect("accounts:login")
    elif merge_guest_into(guest, user):
        messages.success(request, gettext("Your free mock result was added to your account."))
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(_safe_next(request, target=saved.get("next", "")))
