from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.generic import RedirectView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("accounts/", include("accounts.urls")),
    path("exams/", include("exams.urls")),
    path("results/", include("results.urls")),
    path("speaking/", include("speaking.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("admin-dashboard/", include("admin_dashboard.urls")),
    # People type /admin/ by habit; send them to the admin dashboard.
    path("admin/", RedirectView.as_view(pattern_name="admin_dashboard:home", permanent=False)),
    path("", include("core.urls")),
]

if not settings.USE_S3:
    # Public media only (pictures, maps, avatars) — private files (recordings, audio) are streamed by
    # permission-checked views and never live under MEDIA_ROOT. Also needed with DEBUG=False on hosts
    # without a separate file server (Render). With USE_S3 the files come from the bucket instead.
    def public_media(request, path):
        return serve(request, path, document_root=settings.MEDIA_ROOT)

    urlpatterns += [re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$", public_media)]

handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
