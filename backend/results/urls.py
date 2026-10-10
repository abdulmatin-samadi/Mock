from django.urls import path

from . import views

app_name = "results"

urlpatterns = [
    path("<int:pk>/", views.attempt_detail, name="detail"),
    path("full/<int:pk>/", views.full_detail, name="full_detail"),
    path("explain/<int:question_id>/", views.explain, name="explain"),
]
