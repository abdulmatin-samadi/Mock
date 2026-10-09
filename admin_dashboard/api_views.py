from django.db.models import Count, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import User
from core.permissions import IsAdminRole
from dashboard.services import student_stats
from exams import services as exam_services
from exams.models import ExamPart, FullMock, MockExam, Question, SpeakingQuestion, WritingTask
from results.models import ExamAttempt
from speaking import services as speaking_services
from speaking.models import SpeakingSubmission
from speaking.serializers import SpeakingSubmissionSerializer
from writing import services as writing_services
from writing.models import WritingSubmission
from writing.serializers import WritingSubmissionSerializer

from .serializers import (
    AdminAttemptSerializer,
    AdminExamSerializer,
    AdminFullMockSerializer,
    AdminPartSerializer,
    AdminQuestionSerializer,
    AdminSpeakingQuestionSerializer,
    AdminUserSerializer,
    AdminWritingTaskSerializer,
)
from .services import filter_attempts, filter_speaking, filter_writing


class AdminViewSetMixin:
    permission_classes = [IsAdminRole]


class AdminUserViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    """Search: ?search=  Filters: ?role=student|admin&is_active=true|false"""

    serializer_class = AdminUserSerializer
    filterset_fields = ["role", "is_active"]
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["date_joined", "last_login", "email", "first_name"]

    def get_queryset(self):
        return User.objects.annotate(
            exams_completed=Count("exam_attempts", filter=Q(exam_attempts__status=ExamAttempt.Status.COMPLETED),
                                  distinct=True),
        ).order_by("-date_joined")

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError("You cannot delete your own account.")
        # Keep history: deactivate instead of deleting users with results.
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        user = self.get_object()
        attempts = ExamAttempt.objects.filter(student=user).select_related("exam", "result", "student")
        return Response({
            "user": AdminUserSerializer(user, context={"request": request}).data,
            "stats": {k: (float(v) if hasattr(v, "as_tuple") else v)
                      for k, v in student_stats(user).items() if k != "by_section"},
            "attempts": AdminAttemptSerializer(attempts[:100], many=True).data,
            "writing": WritingSubmissionSerializer(
                WritingSubmission.objects.filter(student=user).select_related("task", "attempt__exam", "evaluation"),
                many=True).data,
            "speaking": SpeakingSubmissionSerializer(
                SpeakingSubmission.objects.filter(student=user).select_related("question", "exam", "evaluation"),
                many=True).data,
        })


class AdminExamViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminExamSerializer
    filterset_fields = ["section", "is_published", "level"]
    search_fields = ["title", "description"]

    def get_queryset(self):
        return MockExam.objects.prefetch_related("parts__questions__options", "writing_tasks", "speaking_questions")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, is_published=False)

    def perform_destroy(self, instance):
        if instance.attempts.exists():
            raise ValidationError("This mock has attempts; unpublish it instead of deleting.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        exam = self.get_object()
        problems = exam_services.validate_publishable(exam)
        if problems:
            raise ValidationError({"problems": problems})
        exam.is_published = True
        exam.save(update_fields=["is_published", "updated_at"])
        return Response({"is_published": True})

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        exam = self.get_object()
        exam.is_published = False
        exam.save(update_fields=["is_published", "updated_at"])
        return Response({"is_published": False})

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        copy = exam_services.duplicate_exam(self.get_object(), request.user)
        return Response(AdminExamSerializer(copy).data, status=201)


class AdminExamPartViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminPartSerializer
    queryset = ExamPart.objects.prefetch_related("questions__options")
    filterset_fields = ["exam"]


class AdminQuestionViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminQuestionSerializer
    queryset = Question.objects.prefetch_related("options")
    filterset_fields = ["exam", "part", "question_type"]

    def perform_destroy(self, instance):
        if instance.answers.exists():
            raise ValidationError("This question has student answers and cannot be deleted.")
        instance.delete()


class AdminWritingTaskViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminWritingTaskSerializer
    queryset = WritingTask.objects.all()
    filterset_fields = ["exam", "task_type"]


class AdminSpeakingQuestionViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminSpeakingQuestionSerializer
    queryset = SpeakingQuestion.objects.all()
    filterset_fields = ["exam", "part"]


class AdminResultViewSet(AdminViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """All attempts. Filters: ?section=&type=&status=&date_from=&date_to=&min_score=&max_score=&q="""

    serializer_class = AdminAttemptSerializer
    filter_backends = []

    def get_queryset(self):
        return filter_attempts(self.request.query_params)[0]


class AdminWritingSubmissionViewSet(AdminViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = WritingSubmissionSerializer
    filter_backends = []

    def get_queryset(self):
        return filter_writing(self.request.query_params)[0]

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        writing_services.retry_evaluation(self.get_object())
        return Response({"detail": "Re-queued."})


class AdminSpeakingSubmissionViewSet(AdminViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                     viewsets.GenericViewSet):
    serializer_class = SpeakingSubmissionSerializer
    filter_backends = []

    def get_queryset(self):
        return filter_speaking(self.request.query_params)[0]

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        speaking_services.retry_processing(self.get_object())
        return Response({"detail": "Re-queued."})


class AdminFullMockViewSet(AdminViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AdminFullMockSerializer
    queryset = FullMock.objects.all()
    filterset_fields = ["is_published", "level"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.attempts.exists():
            raise ValidationError("This full mock has sittings; unpublish it instead.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        fm = self.get_object()
        problems = fm.publish_problems()
        if problems:
            raise ValidationError({"problems": problems})
        fm.is_published = True
        fm.save(update_fields=["is_published", "updated_at"])
        return Response({"is_published": True})

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        fm = self.get_object()
        fm.is_published = False
        fm.save(update_fields=["is_published", "updated_at"])
        return Response({"is_published": False})
