"""Student-facing exam serializers. They NEVER include correct answers."""
from django.urls import reverse
from rest_framework import serializers

from .models import ExamPart, FullMock, MockExam, Option, Question, SpeakingQuestion, WritingTask


class OptionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "label", "text"]


class QuestionPublicSerializer(serializers.ModelSerializer):
    options = OptionPublicSerializer(many=True, read_only=True)
    choices = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ["id", "order", "question_type", "prompt", "points", "options", "choices"]

    def get_choices(self, obj):
        return obj.fixed_choices


class PartPublicSerializer(serializers.ModelSerializer):
    questions = QuestionPublicSerializer(many=True, read_only=True)
    audio_url = serializers.SerializerMethodField()

    class Meta:
        model = ExamPart
        fields = ["id", "title", "order", "instructions", "passage", "audio_url", "questions"]

    def get_audio_url(self, obj):
        return reverse("exams:part_audio", args=[obj.pk]) if obj.audio else None


class WritingTaskPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingTask
        fields = ["id", "order", "title", "task_type", "topic", "instructions", "image", "minimum_word_count",
                  "time_limit", "level"]


class SpeakingQuestionPublicSerializer(serializers.ModelSerializer):
    cue_points = serializers.ListField(child=serializers.CharField(), read_only=True)
    part_label = serializers.CharField(source="part_short", read_only=True)
    arguments = serializers.JSONField(read_only=True)

    class Meta:
        model = SpeakingQuestion
        fields = ["id", "part", "part_label", "order", "question", "image", "cue_points", "arguments",
                  "preparation_time", "speaking_time"]


class MockExamListSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = MockExam
        fields = ["id", "title", "description", "section", "level", "time_limit", "question_count",
                  "created_at"]

    def get_question_count(self, obj):
        return obj.question_count()


class MockExamDetailSerializer(MockExamListSerializer):
    audio_url = serializers.SerializerMethodField()
    parts = serializers.SerializerMethodField()
    writing_tasks = serializers.SerializerMethodField()
    speaking_questions = serializers.SerializerMethodField()

    class Meta(MockExamListSerializer.Meta):
        fields = MockExamListSerializer.Meta.fields + ["instructions", "audio_url", "parts", "writing_tasks",
                                                       "speaking_questions"]

    def get_audio_url(self, obj):
        return reverse("exams:audio", args=[obj.pk]) if obj.audio else None

    def get_parts(self, obj):
        if not obj.is_objective:
            return []
        parts = obj.parts.prefetch_related("questions__options")
        return PartPublicSerializer(parts, many=True, context=self.context).data

    def get_writing_tasks(self, obj):
        if obj.section != "writing":
            return []
        return WritingTaskPublicSerializer(obj.writing_tasks.filter(is_published=True), many=True,
                                           context=self.context).data

    def get_speaking_questions(self, obj):
        if obj.section != "speaking":
            return []
        return SpeakingQuestionPublicSerializer(obj.speaking_questions.all(), many=True).data


class FullMockSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()
    total_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = FullMock
        fields = ["id", "title", "description", "level", "total_minutes", "sections", "created_at"]

    def get_sections(self, obj):
        return [{"section": s, "exam": e.pk, "title": e.title, "time_limit": e.time_limit} for s, e in obj.sections()]
