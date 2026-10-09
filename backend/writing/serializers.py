from rest_framework import serializers

from results.serializers import StudentIdentitySerializer

from .models import WritingEvaluation, WritingSubmission


class WritingEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingEvaluation
        exclude = ["raw_response"]
        read_only_fields = [f.name for f in WritingEvaluation._meta.fields]


class WritingSubmissionSerializer(serializers.ModelSerializer):
    student = StudentIdentitySerializer(read_only=True)
    exam = serializers.IntegerField(source="attempt.exam_id", read_only=True)
    exam_title = serializers.CharField(source="attempt.exam.title", read_only=True)
    section = serializers.SerializerMethodField()
    task_title = serializers.CharField(source="task.title", read_only=True)
    task_type = serializers.CharField(source="task.task_type", read_only=True)
    evaluation = WritingEvaluationSerializer(read_only=True)

    class Meta:
        model = WritingSubmission
        fields = ["id", "attempt", "student", "exam", "exam_title", "section", "task", "task_title",
                  "task_type", "essay", "word_count", "status", "error_message", "score", "submitted_at",
                  "evaluated_at", "evaluation"]
        read_only_fields = fields

    def get_section(self, obj):
        return "writing"


class WritingCreateSerializer(serializers.Serializer):
    task = serializers.IntegerField()
    essay = serializers.CharField(max_length=20000, trim_whitespace=True)
