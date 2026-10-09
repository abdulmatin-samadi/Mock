import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import IsOwnerOrAdmin

from . import services
from .models import Answer, ExamAttempt, FullMockAttempt, Result
from .serializers import AnswerSerializer, ExamAttemptSerializer, FullMockAttemptSerializer, ResultSerializer


class AttemptFilter(django_filters.FilterSet):
    section = django_filters.CharFilter(field_name="exam__section")
    date_from = django_filters.DateFilter(field_name="started_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="started_at", lookup_expr="date__lte")
    min_percentage = django_filters.NumberFilter(field_name="percentage", lookup_expr="gte")
    max_percentage = django_filters.NumberFilter(field_name="percentage", lookup_expr="lte")

    class Meta:
        model = ExamAttempt
        fields = ["exam", "status", "section", "date_from", "date_to"]


class AttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/attempts/ — the user's own attempts only.

    PATCH /api/attempts/{id}/answers/  {"answers": {"<question_id>": "<value>"}}  (autosave)
    POST  /api/attempts/{id}/submit/   reading/listening: {"answers": {...}}
                                       writing:           {"essays": {"<task_id>": "text"}}
                                       speaking:          {} (after uploading recordings)
    """

    serializer_class = ExamAttemptSerializer
    permission_classes = [IsOwnerOrAdmin]
    filterset_class = AttemptFilter
    ordering_fields = ["started_at", "submitted_at", "percentage"]

    def get_queryset(self):
        return (ExamAttempt.objects.filter(student=self.request.user)
                .select_related("exam", "student", "result"))

    def _own_attempt(self):
        attempt = self.get_object()
        if attempt.student_id != self.request.user.id:
            raise PermissionDenied
        return attempt

    @action(detail=True, methods=["patch", "post"])
    def answers(self, request, pk=None):
        attempt = self._own_attempt()
        try:
            saved = services.save_answers(attempt, request.data.get("answers") or {})
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        return Response({"saved": saved})

    @action(detail=True, methods=["patch", "post"])
    def drafts(self, request, pk=None):
        """PATCH {"drafts": {"<task_id>": "text"}} — autosave writing drafts."""
        attempt = self._own_attempt()
        try:
            saved = services.save_drafts(attempt, request.data.get("drafts") or {})
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        return Response({"saved": saved})

    def get_throttles(self):
        if self.action == "submit":
            self.throttle_scope = "ai_submit"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        attempt = self._own_attempt()
        try:
            attempt = services.submit_attempt(attempt, request.data)
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        attempt.refresh_from_db()
        return Response(ExamAttemptSerializer(attempt).data)


class AnswerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnswerSerializer
    filterset_fields = ["attempt"]

    def get_queryset(self):
        return Answer.objects.filter(attempt__student=self.request.user).select_related("question", "attempt")


class ResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResultSerializer
    filterset_fields = ["attempt", "cefr_level"]

    def get_queryset(self):
        return Result.objects.filter(attempt__student=self.request.user).select_related("attempt")


class FullMockAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/attempts/full/ — own full mock sittings.
    POST {id}/next/ starts (or resumes) the next section and returns its ExamAttempt."""

    serializer_class = FullMockAttemptSerializer
    filterset_fields = ["status", "full_mock"]

    def get_queryset(self):
        return FullMockAttempt.objects.filter(student=self.request.user).select_related("full_mock", "student")

    @action(detail=True, methods=["post"])
    def next(self, request, pk=None):
        full = self.get_object()
        try:
            attempt = services.start_next_section(full)
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        return Response(ExamAttemptSerializer(attempt).data)
