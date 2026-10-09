from rest_framework import serializers

from . import services
from .models import Answer, ExamAttempt, FullMockAttempt, Result


class StudentIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()


class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ["id", "attempt", "score", "scaled_score", "cefr_level", "feedback", "details", "created_at"]
        read_only_fields = fields


class AnswerSerializer(serializers.ModelSerializer):
    """Correctness and correct answers are only revealed after the attempt is graded."""

    question_number = serializers.IntegerField(source="question.order", read_only=True)
    question_prompt = serializers.CharField(source="question.prompt", read_only=True)
    correct_answer = serializers.SerializerMethodField()
    explanation = serializers.SerializerMethodField()
    is_correct = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()

    class Meta:
        model = Answer
        fields = ["id", "attempt", "question", "question_number", "question_prompt", "answer", "selected_option",
                  "is_correct", "points", "correct_answer", "explanation", "answered_at"]
        read_only_fields = fields

    def _graded(self, obj):
        return obj.attempt.status == ExamAttempt.Status.COMPLETED

    def get_correct_answer(self, obj):
        return obj.question.correct_display() if self._graded(obj) else None

    def get_explanation(self, obj):
        return obj.question.explanation if self._graded(obj) else None

    def get_is_correct(self, obj):
        return obj.is_correct if self._graded(obj) else None

    def get_points(self, obj):
        return obj.points if self._graded(obj) else None


class ExamAttemptSerializer(serializers.ModelSerializer):
    student = StudentIdentitySerializer(read_only=True)
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    section = serializers.CharField(source="exam.section", read_only=True)
    result = ResultSerializer(read_only=True)
    deadline = serializers.SerializerMethodField()
    display_score = serializers.CharField(read_only=True)
    practice_label = serializers.CharField(read_only=True)

    class Meta:
        model = ExamAttempt
        fields = ["id", "student", "exam", "exam_title", "section", "status", "started_at",
                  "submitted_at", "completed_at", "deadline", "score", "max_score", "percentage", "time_spent",
                  "correct_count", "incorrect_count", "unanswered_count", "is_late", "display_score", "result",
                  "practice", "practice_label"]
        read_only_fields = fields

    def get_deadline(self, obj):
        return services.deadline(obj)


class FullMockAttemptSerializer(serializers.ModelSerializer):
    student = StudentIdentitySerializer(read_only=True)
    full_mock_title = serializers.CharField(source="full_mock.title", read_only=True)
    sections = serializers.SerializerMethodField()
    next_section = serializers.SerializerMethodField()

    class Meta:
        model = FullMockAttempt
        fields = ["id", "student", "full_mock", "full_mock_title", "status", "started_at", "completed_at", "score",
                  "cefr_level", "sections", "next_section"]
        read_only_fields = fields

    def get_sections(self, obj):
        out = []
        for section, exam, attempt in services.full_progress(obj):
            result = getattr(attempt, "result", None) if attempt else None
            out.append({"section": section, "exam": exam.pk, "attempt": attempt.pk if attempt else None,
                        "status": attempt.status if attempt else "not_started",
                        "score": result.scaled_score if result else None})
        return out

    def get_next_section(self, obj):
        nxt = services.next_section(obj)
        return nxt[0] if nxt else None
