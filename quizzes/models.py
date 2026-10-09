from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from courses.models import Course, CourseLesson


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    lesson = models.ForeignKey(CourseLesson, on_delete=models.SET_NULL, null=True, blank=True, related_name="quizzes")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    time_limit = models.PositiveIntegerField(default=0, help_text="Minutes (0 = no limit)")
    passing_score = models.PositiveSmallIntegerField(default=60, validators=[MaxValueValidator(100)],
                                                     help_text="Percent required to pass")
    is_published = models.BooleanField("published", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course", "created_at"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title

    def get_course(self):
        return self.course

    def get_absolute_url(self):
        return reverse("quizzes:detail", args=[self.pk])

    @property
    def total_points(self):
        return sum((q.points for q in self.questions.all()), Decimal(0))


class QuizQuestion(models.Model):
    class Type(models.TextChoices):
        SINGLE = "single", "Single choice"
        MULTIPLE = "multiple", "Multiple choice (several correct)"
        TRUE_FALSE = "true_false", "True / False"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question = models.TextField()
    question_type = models.CharField(max_length=16, choices=Type.choices, default=Type.SINGLE)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("1.00"),
                                 validators=[MinValueValidator(Decimal("0.01"))])
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.question[:80]

    def get_course(self):
        return self.quiz.course

    def correct_option_ids(self):
        return {o.pk for o in self.options.all() if o.is_correct}


class QuizOption(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.option_text

    def get_course(self):
        return self.question.quiz.course


class QuizAttempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    max_score = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    passed = models.BooleanField(default=False)
    time_spent = models.PositiveIntegerField(default=0, help_text="Seconds")
    is_late = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.student} — {self.quiz}"

    def get_course(self):
        return self.quiz.course

    def get_absolute_url(self):
        return reverse("quizzes:result", args=[self.pk])


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="+")
    selected_options = models.ManyToManyField(QuizOption, blank=True, related_name="+")
    is_correct = models.BooleanField(default=False)
    points_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="unique_quiz_answer")]
