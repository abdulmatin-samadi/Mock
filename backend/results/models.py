from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _

from exams.models import FullMock, MockExam, Option, Question


class ExamAttempt(models.Model):
    """Universal attempt record for every section (reading/listening/writing/speaking)."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In progress")
        EVALUATING = "evaluating", _("Evaluating")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Evaluation failed")
        DISCARDED = "discarded", _("Discarded")

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    time_spent = models.PositiveIntegerField(default=0, help_text="Seconds")
    correct_count = models.PositiveIntegerField(default=0)
    incorrect_count = models.PositiveIntegerField(default=0)
    unanswered_count = models.PositiveIntegerField(default=0)
    is_late = models.BooleanField(default=False, help_text="Submitted after the time limit (late answers ignored)")
    # Part practice: "part:<ExamPart id>" (reading/listening), "task:<WritingTask id>" (writing),
    # "part:<1-4>" (speaking). Empty = the full section test.
    practice = models.CharField(max_length=32, blank=True, default="")
    time_limit = models.PositiveIntegerField(null=True, blank=True,
                                             help_text="Minutes for this attempt (overrides the exam's)")
    drafts = models.JSONField(default=dict, blank=True, help_text="Unsubmitted writing drafts {task_id: text}")
    drafts_saved_at = models.DateTimeField(null=True, blank=True)
    full_mock_attempt = models.ForeignKey("FullMockAttempt", on_delete=models.CASCADE, null=True, blank=True,
                                          related_name="section_attempts")

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["student", "status"])]

    def __str__(self):
        return f"{self.student.email} · {self.exam.title} · {self.get_status_display()}"

    @property
    def section(self):
        return self.exam.section

    @property
    def is_practice(self):
        return bool(self.practice)

    @property
    def practice_label(self):
        """Human label of the practised part, e.g. "Task 1.1" or "Part 2 · Note completion"."""
        if not self.practice:
            return ""
        kind, _, value = self.practice.partition(":")
        from exams.models import ExamPart, SpeakingQuestion, WritingTask

        if self.exam.section == "speaking":
            return SpeakingQuestion.SHORT_LABELS.get(int(value), f"Part {value}") if value.isdigit() else ""
        if kind == "task":
            task = WritingTask.objects.filter(pk=value).first()
            return task.title if task else ""
        part = ExamPart.objects.filter(pk=value).first()
        return part.title if part else ""

    def get_absolute_url(self):
        return reverse("results:detail", args=[self.pk])

    @property
    def display_score(self):
        """Headline score: Multilevel 0–75 score with CEFR level, or percentage."""
        result = getattr(self, "result", None)
        if result is None:
            return None
        if self.practice and self.exam.is_objective and self.correct_count is not None:
            total = self.correct_count + self.incorrect_count + self.unanswered_count
            return gettext("%(n)d/%(total)d correct") % {"n": self.correct_count, "total": total}
        if result.scaled_score is not None:
            return f"{result.scaled_score:g}/75 · {result.cefr_level}"
        if self.percentage is not None:
            return f"{self.percentage:g}%"
        return None


class Answer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    answer = models.CharField(max_length=500, blank=True)
    selected_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_correct = models.BooleanField(default=False)
    points = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question__part__order", "question__order"]
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="unique_attempt_answer")]

    def __str__(self):
        return f"{self.attempt_id}/Q{self.question.order}: {self.answer}"


class Result(models.Model):
    attempt = models.OneToOneField(ExamAttempt, on_delete=models.CASCADE, related_name="result")
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    scaled_score = models.DecimalField("Multilevel score (0–75)", max_digits=5, decimal_places=1, null=True,
                                       blank=True)
    cefr_level = models.CharField(max_length=16, blank=True)
    feedback = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result #{self.attempt_id}"


class FullMockAttempt(models.Model):
    """One sitting of a full Multilevel test (4 section attempts)."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In progress")
        EVALUATING = "evaluating", _("Evaluating")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Evaluation failed")

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="full_mock_attempts")
    full_mock = models.ForeignKey(FullMock, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField("Overall (0–75)", max_digits=5, decimal_places=1, null=True, blank=True)
    cefr_level = models.CharField(max_length=16, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.student.email} · {self.full_mock.title}"

    def get_absolute_url(self):
        return reverse("results:full_detail", args=[self.pk])

    def section_attempt(self, section):
        return self.section_attempts.filter(exam__section=section).order_by("-started_at").first()


class AnswerExplanation(models.Model):
    """AI-written "why is this the answer" note, shared by every student (one per question and language)."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="ai_explanations")
    language = models.CharField(max_length=8)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["question", "language"], name="unique_explanation_lang")]

    def __str__(self):
        return f"Q{self.question_id} ({self.language})"


class LearnedMistake(models.Model):
    """A question the student marked as learned — it leaves their mistakes notebook."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learned_mistakes")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "question"], name="unique_learned_mistake")]
