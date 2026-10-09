from rest_framework import serializers

from results.serializers import StudentIdentitySerializer

from .models import SpeakingEvaluation, SpeakingSubmission


class SpeakingEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakingEvaluation
        exclude = ["raw_response"]
        read_only_fields = [f.name for f in SpeakingEvaluation._meta.fields]


class SpeakingSubmissionSerializer(serializers.ModelSerializer):
    student = StudentIdentitySerializer(read_only=True)
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    section = serializers.SerializerMethodField()
    question_text = serializers.CharField(source="question.question", read_only=True)
    part = serializers.IntegerField(source="question.part", read_only=True)
    audio_url = serializers.SerializerMethodField()
    evaluation = SpeakingEvaluationSerializer(read_only=True)

    class Meta:
        model = SpeakingSubmission
        fields = ["id", "attempt", "student", "exam", "exam_title", "section", "question",
                  "question_text", "part", "audio_url", "duration", "file_size", "processing_status",
                  "error_message", "transcript", "score", "submitted_at", "processed_at", "evaluation"]
        read_only_fields = fields

    def get_section(self, obj):
        return "speaking"

    def get_audio_url(self, obj):
        return obj.get_audio_url()


class SpeakingUploadSerializer(serializers.Serializer):
    attempt = serializers.IntegerField()
    question = serializers.IntegerField()
    audio_file = serializers.FileField()
    duration = serializers.FloatField(required=False, min_value=0, default=0)
