import os

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.storage import private_storage, speaking_recording_path
from core.validators import validate_recording
from exams.models import MockExam, SpeakingQuestion
from results.models import ExamAttempt


class SpeakingStatus(models.TextChoices):
    PENDING = "pending", _("Uploaded")
    TRANSCRIBING = "transcribing", _("Transcribing")
    EVALUATING = "evaluating", _("Evaluating")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


class SpeakingSubmission(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="speaking_submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="speaking_submissions")
    exam = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="speaking_submissions")
    question = models.ForeignKey(SpeakingQuestion, on_delete=models.PROTECT, related_name="submissions")
    audio_file = models.FileField(upload_to=speaking_recording_path, storage=private_storage,
                                  validators=[validate_recording])
    mime_type = models.CharField(max_length=64, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    duration = models.FloatField(default=0, help_text="Seconds (reported by the recorder)")
    processing_status = models.CharField(max_length=16, choices=SpeakingStatus.choices,
                                         default=SpeakingStatus.PENDING, db_index=True)
    error_message = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    score = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    retries = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["question__part", "question__order", "-submitted_at"]
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="unique_speaking_per_question")]

    def __str__(self):
        return f"{self.student.email} · {self.question}"

    def get_audio_url(self):
        return reverse("speaking:audio", args=[self.pk])

    @property
    def audio_filename(self):
        return os.path.basename(self.audio_file.name)


class SpeakingEvaluation(models.Model):
    """AI evaluation of one spoken response. Pronunciation is only filled in when
    the provider genuinely analysed the audio (pronunciation_assessed=True)."""

    submission = models.OneToOneField(SpeakingSubmission, on_delete=models.CASCADE, related_name="evaluation")
    provider = models.CharField(max_length=32)
    model_name = models.CharField(max_length=100)
    stt_provider = models.CharField(max_length=32, blank=True)
    stt_model = models.CharField(max_length=100, blank=True)
    overall_score = models.DecimalField(max_digits=4, decimal_places=1)
    fluency_score = models.DecimalField("Fluency and coherence", max_digits=4, decimal_places=1)
    vocabulary_score = models.DecimalField("Vocabulary", max_digits=4, decimal_places=1)
    grammar_score = models.DecimalField("Grammar", max_digits=4, decimal_places=1)
    pronunciation_score = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pronunciation_assessed = models.BooleanField(default=False)
    cefr_level = models.CharField(max_length=16, blank=True)
    fluency_feedback = models.TextField(blank=True)
    coherence_feedback = models.TextField(blank=True)
    vocabulary_feedback = models.TextField(blank=True)
    grammar_feedback = models.TextField(blank=True)
    pronunciation_feedback = models.TextField(blank=True)
    detailed_feedback = models.TextField(blank=True)
    mistakes = models.JSONField(default=list, blank=True)
    improvement_suggestions = models.JSONField(default=list, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Speaking evaluation #{self.submission_id}"
