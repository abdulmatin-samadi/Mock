from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("speaking/submissions", api_views.SpeakingSubmissionViewSet, basename="speaking-submission")
router.register("speaking/evaluations", api_views.SpeakingEvaluationViewSet, basename="speaking-evaluation")

urlpatterns = router.urls
