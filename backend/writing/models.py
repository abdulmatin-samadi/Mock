from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from exams.models import WritingTask
from results.models import ExamAttempt


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Evaluating")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


class WritingSubmission(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="writing_submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="writing_submissions")
    task = models.ForeignKey(WritingTask, on_delete=models.PROTECT, related_name="submissions")
    essay = models.TextField()
    word_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING,
                              db_index=True)
    error_message = models.TextField(blank=True)
    score = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    retries = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [models.UniqueConstraint(fields=["attempt", "task"], name="unique_writing_per_task")]

    def __str__(self):
        return f"{self.student.email} · {self.task}"

    def get_absolute_url(self):
        return reverse("dashboard:writing_detail", args=[self.pk])

    @property
    def exam(self):
        return self.attempt.exam


class WritingEvaluation(models.Model):
    """AI evaluation. Written only by the server-side AI pipeline; read-only for users."""

    submission = models.OneToOneField(WritingSubmission, on_delete=models.CASCADE, related_name="evaluation")
    provider = models.CharField(max_length=32)
    model_name = models.CharField(max_length=100)
    overall_score = models.DecimalField(max_digits=4, decimal_places=1)
    task_score = models.DecimalField("Task completion", max_digits=4, decimal_places=1)
    coherence_score = models.DecimalField("Coherence and organisation", max_digits=4, decimal_places=1)
    vocabulary_score = models.DecimalField("Vocabulary", max_digits=4, decimal_places=1)
    grammar_score = models.DecimalField("Grammar", max_digits=4, decimal_places=1)
    cefr_level = models.CharField(max_length=16, blank=True)
    task_feedback = models.TextField(blank=True)
    coherence_feedback = models.TextField(blank=True)
    vocabulary_feedback = models.TextField(blank=True)
    grammar_feedback = models.TextField(blank=True)
    detailed_feedback = models.TextField(blank=True)
    grammar_mistakes = models.JSONField(default=list, blank=True)
    vocabulary_mistakes = models.JSONField(default=list, blank=True)
    suggested_corrections = models.JSONField(default=list, blank=True)
    weak_sentences = models.JSONField(default=list, blank=True)
    strong_sentences = models.JSONField(default=list, blank=True)
    improvement_suggestions = models.JSONField(default=list, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evaluation of submission #{self.submission_id}"
