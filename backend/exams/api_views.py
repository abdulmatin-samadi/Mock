from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.media import serve_private_file
from results import services as result_services
from results.serializers import ExamAttemptSerializer

from .models import ExamPart, FullMock, MockExam
from .serializers import FullMockSerializer, MockExamDetailSerializer, MockExamListSerializer
from .services import can_access_exam_media


class ExamViewSet(viewsets.ReadOnlyModelViewSet):
    """Published mock exams. Subclasses fix the section (/api/exams/reading/ …)."""

    section = None
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["section", "level"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "title"]

    def get_queryset(self):
        qs = MockExam.objects.published()
        if self.section:
            qs = qs.filter(section=self.section)
        return qs

    def get_serializer_class(self):
        return MockExamDetailSerializer if self.action == "retrieve" else MockExamListSerializer

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start (or resume) an attempt; optional {"practice": "<key>"} from /practice-options/."""
        exam = self.get_object()
        try:
            attempt, created = result_services.start_attempt(request.user, exam,
                                                             practice=request.data.get("practice", "") or "")
        except DjangoPermissionDenied as e:
            raise PermissionDenied(str(e))
        except DjangoValidationError as e:
            raise ValidationError(e.messages)
        return Response(ExamAttemptSerializer(attempt).data, status=201 if created else 200)

    @action(detail=True, methods=["get"], url_path="practice-options")
    def practice_options(self, request, pk=None):
        """Parts that can be practised on their own (Part Practice mode)."""
        return Response(result_services.practice_options(self.get_object()))

    @action(detail=True, methods=["get"])
    def audio(self, request, pk=None):
        exam = self.get_object()
        if not can_access_exam_media(request.user, exam):
            raise PermissionDenied
        return serve_private_file(request, exam.audio)

    @action(detail=True, methods=["get"], url_path=r"parts/(?P<part_id>\d+)/audio")
    def part_audio(self, request, pk=None, part_id=None):
        exam = self.get_object()
        if not can_access_exam_media(request.user, exam):
            raise PermissionDenied
        part = get_object_or_404(ExamPart, pk=part_id, exam=exam)
        return serve_private_file(request, part.audio)


class ReadingExamViewSet(ExamViewSet):
    section = "reading"


class ListeningExamViewSet(ExamViewSet):
    section = "listening"


class WritingExamViewSet(ExamViewSet):
    section = "writing"


class SpeakingExamViewSet(ExamViewSet):
    section = "speaking"


class FullMockViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/exams/full/ — published full mocks. POST {id}/start/ starts or resumes a sitting."""

    serializer_class = FullMockSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["level"]

    def get_queryset(self):
        return FullMock.objects.filter(is_published=True).select_related("listening", "reading", "writing",
                                                                          "speaking")

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        from results.serializers import FullMockAttemptSerializer

        try:
            full, created = result_services.start_full_mock(request.user, self.get_object())
        except DjangoPermissionDenied as e:
            raise PermissionDenied(str(e))
        return Response(FullMockAttemptSerializer(full).data, status=201 if created else 200)
