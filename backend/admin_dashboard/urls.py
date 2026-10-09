from django.urls import path

from . import views

app_name = "admin_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    # users
    path("users/", views.users, name="users"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    # mocks
    path("mocks/<int:pk>/", views.mock_manage, name="mock_manage"),
    path("mocks/<int:pk>/edit/", views.mock_edit, name="mock_edit"),
    path("mocks/<int:pk>/delete/", views.mock_delete, name="mock_delete"),
    path("mocks/<int:pk>/publish/", views.mock_toggle_publish, name="mock_publish"),
    path("mocks/<int:pk>/duplicate/", views.mock_duplicate, name="mock_duplicate"),
    path("mocks/<int:exam_pk>/parts/new/", views.part_form, name="part_create"),
    path("parts/<int:pk>/edit/", views.part_form, name="part_edit"),
    path("parts/<int:pk>/quick/", views.quick_part, name="quick_part"),
    path("mocks/<int:exam_pk>/quick-speaking/", views.quick_speaking, name="quick_speaking"),
    path("mocks/<int:exam_pk>/quick-writing/", views.quick_writing, name="quick_writing"),
    path("parts/<int:pk>/delete/", views.part_delete, name="part_delete"),
    path("parts/<int:part_pk>/questions/new/", views.question_form, name="question_create"),
    path("questions/<int:pk>/edit/", views.question_form, name="question_edit"),
    path("questions/<int:pk>/delete/", views.question_delete, name="question_delete"),
    path("mocks/<int:exam_pk>/tasks/new/", views.task_form, name="task_create"),
    path("tasks/<int:pk>/edit/", views.task_form, name="task_edit"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("mocks/<int:exam_pk>/speaking-questions/new/", views.speaking_question_form,
         name="speaking_question_create"),
    path("speaking-questions/<int:pk>/edit/", views.speaking_question_form, name="speaking_question_edit"),
    path("speaking-questions/<int:pk>/delete/", views.speaking_question_delete, name="speaking_question_delete"),
    path("full-mocks/", views.full_mocks, name="full_mocks"),
    path("full-mocks/new/", views.full_mock_form, name="full_mock_create"),
    path("full-mocks/<int:pk>/", views.full_mock_detail, name="full_mock_detail"),
    path("full-mocks/<int:pk>/edit/", views.full_mock_form, name="full_mock_edit"),
    path("full-mocks/<int:pk>/publish/", views.full_mock_publish, name="full_mock_publish"),
    path("full-mocks/<int:pk>/delete/", views.full_mock_delete, name="full_mock_delete"),
    path("mocks/section/<str:section>/", views.mocks, name="mocks"),
    path("mocks/section/<str:section>/new/", views.mock_create, name="mock_create"),
    # submissions & results
    path("writing/", views.writing_submissions, name="writing"),
    path("writing/<int:pk>/", views.writing_detail, name="writing_detail"),
    path("writing/<int:pk>/retry/", views.writing_retry, name="writing_retry"),
    path("speaking/", views.speaking_submissions, name="speaking"),
    path("speaking/<int:pk>/", views.speaking_detail, name="speaking_detail"),
    path("speaking/<int:pk>/retry/", views.speaking_retry, name="speaking_retry"),
    path("results/", views.results, name="results"),
    path("settings/", views.settings_page, name="settings"),
]
