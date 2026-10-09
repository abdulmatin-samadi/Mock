from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("exams/full", api_views.FullMockViewSet, basename="full-mock")
router.register("exams/reading", api_views.ReadingExamViewSet, basename="exam-reading")
router.register("exams/listening", api_views.ListeningExamViewSet, basename="exam-listening")
router.register("exams/writing", api_views.WritingExamViewSet, basename="exam-writing")
router.register("exams/speaking", api_views.SpeakingExamViewSet, basename="exam-speaking")
router.register("exams", api_views.ExamViewSet, basename="exam")

urlpatterns = router.urls
