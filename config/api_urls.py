"""Root of the REST API (/api/). Order matters: nested prefixes such as
courses/lessons/ must be registered before the courses/<pk>/ routes."""
from django.urls import include, path

urlpatterns = [
    path("", include("accounts.api_urls")),         # auth/, users/
    path("", include("exams.api_urls")),            # exams/, exams/<section>/
    path("", include("results.api_urls")),          # attempts/, answers/, results/
    path("", include("writing.api_urls")),          # writing/submissions|evaluations/
    path("", include("speaking.api_urls")),         # speaking/submissions|evaluations/
    path("admin/", include("admin_dashboard.api_urls")),
]
