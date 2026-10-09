from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import is_admin
from exams.models import WritingTask
from results import services as result_services

from .models import WritingEvaluation, WritingSubmission
from .serializers import WritingCreateSerializer, WritingEvaluationSerializer, WritingSubmissionSerializer


class WritingSubmissionViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """GET: own submissions (admins: all). POST {task, essay}: submit a single task —
    starts/resumes the attempt for that task's exam and queues AI evaluation.
    (Multi-task exams are normally submitted via POST /api/attempts/{id}/submit/.)"""

    serializer_class = WritingSubmissionSerializer
    filterset_fields = ["status", "task", "attempt", "attempt__exam"]
    search_fields = ["student__first_name", "student__last_name", "student__email", "task__title"]
    ordering_fields = ["submitted_at", "score"]

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "ai_submit"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = WritingSubmission.objects.select_related("student", "task", "attempt__exam", "evaluation")
        return qs if is_admin(self.request.user) else qs.filter(student=self.request.user)

    def create(self, request, *args, **kwargs):
        s = WritingCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        task = get_object_or_404(WritingTask.objects.select_related("exam"), pk=s.validated_data["task"],
                                 is_published=True, exam__is_published=True)
        try:
            attempt, _ = result_services.start_attempt(request.user, task.exam)
            attempt, subs = result_services.submit_writing(attempt, {str(task.pk): s.validated_data["essay"]})
        except DjangoPermissionDenied as e:
            raise PermissionDenied(str(e))
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        sub = next(x for x in subs if x.task_id == task.pk)
        return Response(WritingSubmissionSerializer(sub).data, status=201)


class WritingEvaluationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WritingEvaluationSerializer
    filterset_fields = ["submission", "cefr_level"]

    def get_queryset(self):
        qs = WritingEvaluation.objects.select_related("submission")
        return qs if is_admin(self.request.user) else qs.filter(submission__student=self.request.user)
