from django.conf import settings
from django.utils import translation

# The admin pages (content management) stay in English.
ENGLISH_ONLY = ("/admin-dashboard/", "/django-admin/")


class LanguageMiddleware:
    """Uzbek by default; the language switch stores the visitor's choice in a cookie.
    Unlike Django's LocaleMiddleware the browser's Accept-Language is ignored, so everyone starts in Uzbek."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.codes = {code for code, _ in settings.LANGUAGES}

    def __call__(self, request):
        lang = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if request.path.startswith(ENGLISH_ONLY):
            lang = "en"
        elif lang not in self.codes:
            lang = settings.LANGUAGE_CODE
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", lang)
        translation.deactivate()
        return response
