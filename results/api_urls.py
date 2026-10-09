from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("attempts/full", api_views.FullMockAttemptViewSet, basename="full-attempt")
router.register("attempts", api_views.AttemptViewSet, basename="attempt")
router.register("answers", api_views.AnswerViewSet, basename="answer")
router.register("results", api_views.ResultViewSet, basename="result")

urlpatterns = router.urls
