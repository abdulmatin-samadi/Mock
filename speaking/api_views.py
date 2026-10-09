from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.media import serve_private_file
from core.permissions import is_admin
from exams.models import SpeakingQuestion
from results.models import ExamAttempt

from . import services
from .models import SpeakingEvaluation, SpeakingSubmission
from .serializers import SpeakingEvaluationSerializer, SpeakingSubmissionSerializer, SpeakingUploadSerializer


class SpeakingSubmissionViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """GET: own recordings (admins: all).
    POST multipart {attempt, question, audio_file, duration}: upload one answer.
    GET /{id}/audio/: stream the recording (owner or admin only)."""

    serializer_class = SpeakingSubmissionSerializer
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["processing_status", "exam", "attempt", "question__part"]
    search_fields = ["student__first_name", "student__last_name", "student__email", "exam__title"]
    ordering_fields = ["submitted_at", "score"]

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "ai_submit"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = SpeakingSubmission.objects.select_related("student", "exam", "question", "evaluation")
        return qs if is_admin(self.request.user) else qs.filter(student=self.request.user)

    def create(self, request, *args, **kwargs):
        s = SpeakingUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        attempt = get_object_or_404(ExamAttempt, pk=s.validated_data["attempt"], student=request.user)
        question = get_object_or_404(SpeakingQuestion, pk=s.validated_data["question"])
        try:
            sub = services.save_recording(user=request.user, attempt=attempt, question=question,
                                          audio=s.validated_data["audio_file"], duration=s.validated_data["duration"])
        except DjangoPermissionDenied as e:
            raise PermissionDenied(str(e))
        except DjangoValidationError as e:
            raise ValidationError({"audio_file": e.messages})
        return Response(SpeakingSubmissionSerializer(sub).data, status=201)

    @action(detail=True, methods=["get"])
    def audio(self, request, pk=None):
        sub = self.get_object()
        if not services.can_access_recording(request.user, sub):
            raise PermissionDenied
        return serve_private_file(request, sub.audio_file, content_type=sub.mime_type or None)


class SpeakingEvaluationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SpeakingEvaluationSerializer
    filterset_fields = ["submission", "cefr_level"]

    def get_queryset(self):
        qs = SpeakingEvaluation.objects.select_related("submission")
        return qs if is_admin(self.request.user) else qs.filter(submission__student=self.request.user)
