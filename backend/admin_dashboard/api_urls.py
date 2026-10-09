from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("users", api_views.AdminUserViewSet, basename="admin-user")
router.register("exams", api_views.AdminExamViewSet, basename="admin-exam")
router.register("full-mocks", api_views.AdminFullMockViewSet, basename="admin-full-mock")
router.register("exam-parts", api_views.AdminExamPartViewSet, basename="admin-exam-part")
router.register("questions", api_views.AdminQuestionViewSet, basename="admin-question")
router.register("writing-tasks", api_views.AdminWritingTaskViewSet, basename="admin-writing-task")
router.register("speaking-questions", api_views.AdminSpeakingQuestionViewSet, basename="admin-speaking-question")
router.register("results", api_views.AdminResultViewSet, basename="admin-result")
router.register("writing-submissions", api_views.AdminWritingSubmissionViewSet, basename="admin-writing-submission")
router.register("speaking-submissions", api_views.AdminSpeakingSubmissionViewSet,
                basename="admin-speaking-submission")

urlpatterns = router.urls
