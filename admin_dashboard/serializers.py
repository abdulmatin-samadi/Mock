"""Admin-only serializers (full data, including correct answers)."""
from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers

from accounts.models import User
from exams.models import ExamPart, FullMock, MockExam, Option, Question, SpeakingQuestion, WritingTask
from results.serializers import ExamAttemptSerializer


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    exams_completed = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "is_active", "profile_photo", "phone_number",
                  "date_joined", "last_login",
                  "exams_completed", "password"]
        read_only_fields = ["date_joined", "last_login"]

    def validate(self, attrs):
        request = self.context["request"]
        if self.instance and self.instance.pk == request.user.pk:
            if attrs.get("role", User.Role.ADMIN) != User.Role.ADMIN or attrs.get("is_active") is False:
                raise serializers.ValidationError("You cannot demote or deactivate yourself.")
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Required for new users."})
        if attrs.get("password"):
            password_validation.validate_password(attrs["password"])
        return attrs

    def create(self, validated):
        password = validated.pop("password")
        return User.objects.create_user(password=password, **validated)

    def update(self, instance, validated):
        password = validated.pop("password", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        if instance.role != User.Role.ADMIN:
            instance.is_superuser = False
        instance.save()
        return instance


class AdminOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "label", "text", "is_correct", "order"]
        read_only_fields = ["id"]


class AdminQuestionSerializer(serializers.ModelSerializer):
    options = AdminOptionSerializer(many=True, required=False)
    exam = serializers.IntegerField(source="exam_id", read_only=True)

    class Meta:
        model = Question
        fields = ["id", "exam", "part", "order", "question_type", "prompt", "correct_answer", "points",
                  "explanation", "options"]

    def validate(self, attrs):
        qtype = attrs.get("question_type", getattr(self.instance, "question_type", None))
        answer = (attrs.get("correct_answer", getattr(self.instance, "correct_answer", "")) or "").strip()
        options = attrs.get("options")
        if qtype in Question.FIXED_CHOICES and answer.upper() not in Question.FIXED_CHOICES[qtype]:
            raise serializers.ValidationError({"correct_answer": f"Use one of {Question.FIXED_CHOICES[qtype]}."})
        if qtype == Question.Type.MULTIPLE_CHOICE and options is not None:
            if len(options) < 2 or not any(o.get("is_correct") for o in options):
                raise serializers.ValidationError({"options": "Need ≥2 options with one marked correct."})
        if qtype in Question.LABEL_TYPES and options is not None:
            if answer.upper() not in {o["label"].upper() for o in options}:
                raise serializers.ValidationError({"correct_answer": "Must be one of the option labels."})
        if qtype in Question.TEXT_TYPES and not answer:
            raise serializers.ValidationError({"correct_answer": "Required."})
        if qtype in Question.FIXED_CHOICES or qtype in Question.LABEL_TYPES:
            attrs["correct_answer"] = answer.upper()
        return attrs

    @transaction.atomic
    def create(self, validated):
        options = validated.pop("options", [])
        q = Question.objects.create(**validated)
        for i, o in enumerate(options):
            Option.objects.create(question=q, order=o.pop("order", i), **o)
        return q

    @transaction.atomic
    def update(self, instance, validated):
        options = validated.pop("options", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        if options is not None:
            instance.options.all().delete()
            for i, o in enumerate(options):
                Option.objects.create(question=instance, order=o.pop("order", i), **o)
        return instance


class AdminPartSerializer(serializers.ModelSerializer):
    questions = AdminQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = ExamPart
        fields = ["id", "exam", "cefr_part", "title", "summary", "order", "instructions", "passage", "image", "audio",
                  "transcript", "questions"]


class AdminWritingTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = WritingTask
        fields = "__all__"


class AdminSpeakingQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakingQuestion
        fields = "__all__"


class AdminExamSerializer(serializers.ModelSerializer):
    parts = AdminPartSerializer(many=True, read_only=True)
    writing_tasks = AdminWritingTaskSerializer(many=True, read_only=True)
    speaking_questions = AdminSpeakingQuestionSerializer(many=True, read_only=True)
    attempts_count = serializers.SerializerMethodField()

    class Meta:
        model = MockExam
        fields = ["id", "title", "description", "instructions", "section", "level", "time_limit",
                  "audio", "transcript", "is_published", "created_by", "created_at", "updated_at", "attempts_count",
                  "parts", "writing_tasks", "speaking_questions"]
        read_only_fields = ["is_published", "created_by", "created_at", "updated_at"]

    def get_attempts_count(self, obj):
        return obj.attempts.count()


class AdminAttemptSerializer(ExamAttemptSerializer):
    pass


class AdminFullMockSerializer(serializers.ModelSerializer):
    class Meta:
        model = FullMock
        fields = ["id", "title", "description", "level", "listening", "reading", "writing", "speaking",
                  "is_published", "created_at", "updated_at"]
        read_only_fields = ["is_published", "created_at", "updated_at"]

    def validate(self, attrs):
        for section in FullMock.SECTION_ORDER:
            exam = attrs.get(section)
            if exam is not None and exam.section != section:
                raise serializers.ValidationError({section: f"Choose a {section} mock."})
        return attrs
