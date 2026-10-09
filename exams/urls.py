from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("full/", views.full_list, name="full_list"),
    path("full/<int:pk>/", views.full_detail, name="full_detail"),
    path("full/<int:pk>/start/", views.full_start, name="full_start"),
    path("full/attempt/<int:pk>/", views.full_progress, name="full_progress"),
    path("attempt/<int:pk>/", views.take, name="take"),
    path("attempt/<int:pk>/discard/", views.discard, name="discard"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/start/", views.start, name="start"),
    path("<int:pk>/practice/", views.practice, name="practice"),
    path("secure/<int:pk>/audio/", views.exam_audio, name="audio"),
    path("secure/parts/<int:pk>/audio/", views.part_audio, name="part_audio"),
    path("<str:section>/", views.section_list, name="section"),
]
