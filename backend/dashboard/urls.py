from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("results/", views.results, name="results"),
    path("writing/", views.writing_history, name="writing"),
    path("writing/<int:pk>/", views.writing_detail, name="writing_detail"),
    path("speaking/", views.speaking_history, name="speaking"),
    path("mistakes/", views.mistakes, name="mistakes"),
    path("mistakes/<int:question_id>/check/", views.mistake_check, name="mistake_check"),
    path("mistakes/<int:question_id>/learned/", views.mistake_learned, name="mistake_learned"),
]
