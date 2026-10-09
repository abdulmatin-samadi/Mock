import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.storage import course_thumbnail_path, lesson_material_path, lesson_video_path, private_storage
from core.validators import validate_document, validate_image, validate_video


class Course(models.Model):
    class Category(models.TextChoices):
        GENERAL = "general_english", "General English"
        IELTS = "ielts", "IELTS"
        SPEAKING = "speaking", "Speaking"
        WRITING = "writing", "Writing"
        READING = "reading", "Reading"
        LISTENING = "listening", "Listening"
        GRAMMAR = "grammar", "Grammar"
        VOCABULARY = "vocabulary", "Vocabulary"
        MULTILEVEL = "multilevel", "Multilevel"

    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        ELEMENTARY = "elementary", "Elementary"
        PRE_INTERMEDIATE = "pre_intermediate", "Pre-Intermediate"
        INTERMEDIATE = "intermediate", "Intermediate"
        UPPER_INTERMEDIATE = "upper_intermediate", "Upper-Intermediate"
        ADVANCED = "advanced", "Advanced"
        IELTS = "ielts", "IELTS"
        MULTILEVEL = "multilevel", "Multilevel / CEFR"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to=course_thumbnail_path, blank=True, validators=[validate_image])
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="courses", limit_choices_to={"role": "teacher"})
    category = models.CharField(max_length=32, choices=Category.choices, default=Category.GENERAL, db_index=True)
    level = models.CharField(max_length=32, choices=Level.choices, default=Level.INTERMEDIATE, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                validators=[MinValueValidator(0)])
    is_free = models.BooleanField(default=True)
    duration = models.CharField(max_length=60, blank=True, help_text="e.g. '6 weeks' or '12 hours'")
    language = models.CharField(max_length=60, default="English")
    is_published = models.BooleanField(default=False, db_index=True)
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "course"
            slug, n = base, 2
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        if self.is_free:
            self.price = Decimal("0.00")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("courses:detail", args=[self.slug])

    def get_course(self):
        return self

    def published_lessons(self):
        return self.lessons.filter(is_published=True)


class CourseLesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video = models.FileField(upload_to=lesson_video_path, storage=private_storage, blank=True,
                             validators=[validate_video])
    video_url = models.URLField(blank=True, help_text="YouTube or Vimeo link (used if no video file is uploaded)")
    material = models.FileField("PDF / material", upload_to=lesson_material_path, storage=private_storage,
                                blank=True, validators=[validate_document])
    order = models.PositiveIntegerField(default=0, db_index=True)
    duration = models.PositiveIntegerField(default=0, help_text="Minutes")
    is_free_preview = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    def get_course(self):
        return self.course

    def get_absolute_url(self):
        return reverse("courses:lesson", args=[self.course.slug, self.pk])

    @property
    def embed_url(self):
        """Safe embeddable URL for YouTube/Vimeo links; None for other hosts."""
        url = self.video_url or ""
        m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{6,20})", url)
        if m:
            return f"https://www.youtube-nocookie.com/embed/{m.group(1)}"
        m = re.search(r"vimeo\.com/(?:video/)?(\d+)", url)
        if m:
            return f"https://player.vimeo.com/video/{m.group(1)}"
        return None

    @property
    def material_filename(self):
        import os

        return os.path.basename(self.material.name) if self.material else ""


class Enrollment(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completion_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_lesson = models.ForeignKey(CourseLesson, on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name="+")
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-enrolled_at"]
        constraints = [models.UniqueConstraint(fields=["student", "course"], name="unique_enrollment")]

    def __str__(self):
        return f"{self.student} → {self.course}"

    def get_course(self):
        return self.course

    @property
    def completed_lessons(self):
        return CourseProgress.objects.filter(student_id=self.student_id, course_id=self.course_id,
                                             is_completed=True, lesson__is_published=True).count()

    @property
    def total_lessons(self):
        return self.course.lessons.filter(is_published=True).count()


class CourseProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="progress_records")
    lesson = models.ForeignKey(CourseLesson, on_delete=models.CASCADE, related_name="progress_records")
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    watch_progress = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"),
                                         help_text="Percent of the video watched")
    last_watched_position = models.FloatField(default=0, help_text="Seconds")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "lesson"], name="unique_lesson_progress")]

    def get_course(self):
        return self.course


class Certificate(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="certificate")
    code = models.CharField(max_length=32, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:16].upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("courses:certificate", args=[self.code])
