from django.conf import settings

from .quotes import quote_of_the_day


def site(request):
    user = getattr(request, "user", None)
    shell = bool(user and user.is_authenticated and user.is_student)
    return {
        "SITE_NAME": settings.SITE_NAME,
        # Logged-in students get the app shell (sidebar) instead of the public top bar.
        "shell": shell,
        "daily_quote": quote_of_the_day() if shell else None,
    }
