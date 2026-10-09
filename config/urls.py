from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
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

if settings.DEBUG:
    # Public media only. Private media is never served from a static URL.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
