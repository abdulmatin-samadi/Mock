from rest_framework.routers import SimpleRouter

from . import api_views

router = SimpleRouter()
router.register("writing/submissions", api_views.WritingSubmissionViewSet, basename="writing-submission")
router.register("writing/evaluations", api_views.WritingEvaluationViewSet, basename="writing-evaluation")

urlpatterns = router.urls
