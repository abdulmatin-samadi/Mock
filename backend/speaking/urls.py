from django.urls import path

from . import views

app_name = "speaking"

urlpatterns = [
    path("recordings/<int:pk>/audio/", views.recording_audio, name="audio"),
]
