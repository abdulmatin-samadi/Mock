from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from core.storage import listening_audio_path, private_storage, writing_image_path
from core.validators import validate_audio, validate_image


class Section(models.TextChoices):
    READING = "reading", "Reading"
    LISTENING = "listening", "Listening"
    WRITING = "writing", "Writing"
    SPEAKING = "speaking", "Speaking"


class CEFR(models.TextChoices):
    ANY = "", "Mixed / any level"
    A1 = "A1", "A1"
    A2 = "A2", "A2"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    C1 = "C1", "C1"
    C2 = "C2", "C2"


class MockExamQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)


class MockExam(models.Model):
    """One section of a Multilevel (CEFR) mock test (e.g. "Multilevel Mock #4 — Reading")."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    summary = models.CharField(max_length=80, blank=True,
                               help_text="Short topic shown on the mock card (Writing: the Part 1 situation)")
    instructions = models.TextField(blank=True)
    section = models.CharField(max_length=16, choices=Section.choices, db_index=True)
    level = models.CharField(max_length=2, choices=CEFR.choices, blank=True, default="")
    time_limit = models.PositiveIntegerField(default=60, help_text="Minutes (0 = untimed)")
    # Listening: one audio for the whole test (sections may also have their own)
    audio = models.FileField(upload_to=listening_audio_path, storage=private_storage, blank=True,
                             validators=[validate_audio])
    transcript = models.TextField(blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MockExamQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["section", "is_published"])]

    def __str__(self):
        return f"{self.title} ({self.get_section_display()})"

    def get_absolute_url(self):
        return reverse("exams:detail", args=[self.pk])

    @property
    def is_objective(self):
        return self.section in (Section.READING, Section.LISTENING)

    def total_points(self):
        return sum((q.points for q in Question.objects.filter(exam=self)), Decimal(0))

    def question_count(self):
        if self.section == Section.WRITING:
            return self.writing_tasks.filter(is_published=True).count()
        if self.section == Section.SPEAKING:
            return self.speaking_questions.count()
        return Question.objects.filter(exam=self).count()


class ExamPart(models.Model):
    """Reading passage or Listening section."""

    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="parts")
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=80, blank=True, help_text="Short topic shown on the mock card")
    order = models.PositiveIntegerField(default=1)
    cefr_part = models.CharField("CEFR part", max_length=4, blank=True, default="",
                                 help_text="Which official Multilevel part this is (sets the allowed question types)")
    instructions = models.TextField(blank=True)
    passage = models.TextField(blank=True, help_text="Reading passage text (Reading only)")
    audio = models.FileField(upload_to=listening_audio_path, storage=private_storage, blank=True,
                             validators=[validate_audio], help_text="Optional per-section audio (Listening)")
    image = models.ImageField(upload_to=writing_image_path, blank=True, validators=[validate_image],
                              help_text="Map / diagram for labelling questions")
    transcript = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} — {self.title}"


class Question(models.Model):
    class Type(models.TextChoices):
        """Multilevel (CEFR) Reading & Listening question types."""

        GAP_FILLING = "gap_filling", "Gap filling (one word / number)"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        TFNG = "true_false_not_given", "True / False / No Information"
        MATCHING = "matching", "Matching (statements / speakers)"
        HEADINGS = "headings", "Matching headings"
        MAP_LABELLING = "map_labelling", "Map labelling"

    CHOICE_TYPES = {Type.MULTIPLE_CHOICE, Type.MATCHING, Type.HEADINGS, Type.MAP_LABELLING}
    LABEL_TYPES = {Type.MATCHING, Type.HEADINGS, Type.MAP_LABELLING}  # answer = an option label
    TEXT_TYPES = {Type.GAP_FILLING}
    FIXED_CHOICES = {
        Type.TFNG: ["TRUE", "FALSE", "NO INFORMATION"],
    }
    # Other spellings admins or older attempts may use for the same TFNG choice.
    CHOICE_ALIASES = {"T": "TRUE", "F": "FALSE", "NOT GIVEN": "NO INFORMATION", "NG": "NO INFORMATION",
                      "NI": "NO INFORMATION", "NO INFO": "NO INFORMATION"}

    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="questions", editable=False)
    part = models.ForeignKey(ExamPart, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(default=1, help_text="Question number")
    question_type = models.CharField(max_length=32, choices=Type.choices, default=Type.GAP_FILLING)
    prompt = models.TextField(help_text="Question text. For a gap inside the part text just write e.g. \"Gap 1\".")
    correct_answer = models.CharField(
        max_length=500, blank=True,
        help_text="Gap filling: accepted answers separated by | (e.g. 1990|nineteen ninety). "
                  "True/False/No Information: TRUE, FALSE or NO INFORMATION. Matching / headings / map: the option "
                  "label (e.g. C). Multiple choice uses the option marked correct.")
    points = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("1.00"),
                                 validators=[MinValueValidator(Decimal("0.01"))])
    explanation = models.TextField(blank=True, help_text="Shown to the student after submission")

    class Meta:
        ordering = ["part__order", "order", "id"]

    def __str__(self):
        return f"Q{self.order}: {self.prompt[:60]}"

    def save(self, *args, **kwargs):
        self.exam_id = self.part.exam_id
        super().save(*args, **kwargs)

    @classmethod
    def canonical_choice(cls, text):
        value = " ".join(str(text or "").upper().split())
        return cls.CHOICE_ALIASES.get(value, value)

    @property
    def fixed_choices(self):
        return self.FIXED_CHOICES.get(self.question_type)

    @property
    def uses_options(self):
        return self.question_type in self.CHOICE_TYPES

    def correct_display(self):
        if self.question_type == self.Type.MULTIPLE_CHOICE:
            return ", ".join(f"{o.label}. {o.text}" for o in self.options.all() if o.is_correct)
        return self.correct_answer.replace("|", " / ")


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=8, help_text="A, B, C… or i, ii, iii…")
    text = models.CharField(max_length=500, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.label}. {self.text}"


class WritingTask(models.Model):
    class TaskType(models.TextChoices):
        TASK1_1 = "task1_1", "Task 1.1 — Informal letter"
        TASK1_2 = "task1_2", "Task 1.2 — Formal letter"
        TASK2 = "task2", "Task 2 — Essay"

    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="writing_tasks")
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    task_type = models.CharField(max_length=16, choices=TaskType.choices, default=TaskType.TASK2)
    summary = models.CharField(max_length=80, blank=True,
                               help_text="Short line for the mock card, e.g. 'informal letter · to friend'")
    topic = models.TextField(help_text="The question / prompt the student must answer")
    instructions = models.TextField(blank=True)
    image = models.ImageField(upload_to=writing_image_path, blank=True, validators=[validate_image],
                              help_text="Chart/diagram for Task 1")
    minimum_word_count = models.PositiveIntegerField(default=150)
    maximum_word_count = models.PositiveIntegerField(null=True, blank=True,
                                                     help_text="Upper end of the target range (optional)")
    time_limit = models.PositiveIntegerField(default=20, help_text="Suggested minutes for this task")
    level = models.CharField(max_length=2, choices=CEFR.choices, blank=True, default="")
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} — {self.title}"



class SpeakingQuestion(models.Model):
    class Part(models.IntegerChoices):
        """Official Multilevel speaking structure (8 questions)."""

        PART1_1 = 1, "Part 1.1 — Personal questions"
        PART1_2 = 2, "Part 1.2 — Picture comparison"
        PART2 = 3, "Part 2 — Long turn"
        PART3 = 4, "Part 3 — Argument"

    SHORT_LABELS = {1: "Part 1.1", 2: "Part 1.2", 3: "Part 2", 4: "Part 3"}
    DEFAULT_TIMES = {1: (5, 30), 2: (10, 45), 3: (60, 120), 4: (60, 120)}

    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="speaking_questions")
    part = models.PositiveSmallIntegerField(choices=Part.choices, default=Part.PART1_1)
    order = models.PositiveIntegerField(default=1)
    question = models.TextField()
    summary = models.CharField(max_length=80, blank=True,
                               help_text="Topic of this part for the mock card (set it on the first question)")
    cue_card_points = models.TextField(blank=True, help_text="Part 2: one prompt per line. Part 3: arguments, "
                                                         "one per line, starting with 'For:' or 'Against:'")
    image = models.ImageField(upload_to=writing_image_path, blank=True, validators=[validate_image],
                              help_text="Part 1.2: the two pictures to compare (one combined image)")
    preparation_time = models.PositiveIntegerField(default=5, help_text="Seconds")
    speaking_time = models.PositiveIntegerField(default=30, help_text="Seconds")

    class Meta:
        ordering = ["part", "order", "id"]

    def __str__(self):
        return f"{self.part_short} · {self.question[:60]}"

    @property
    def part_short(self):
        return self.SHORT_LABELS.get(self.part, f"Part {self.part}")

    @property
    def arguments(self):
        """Part 3 'For:' / 'Against:' lines split into two columns."""
        pros, cons = [], []
        for line in self.cue_points:
            low = line.lower()
            if low.startswith("for:"):
                pros.append(line[4:].strip())
            elif low.startswith("against:"):
                cons.append(line[8:].strip())
        return {"for": pros, "against": cons} if (pros or cons) else None

    @property
    def cue_points(self):
        return [line.strip("-• ").strip() for line in self.cue_card_points.splitlines() if line.strip()]


class FullMock(models.Model):
    """A complete Multilevel test: one mock of each skill, taken in the official order."""

    SECTION_ORDER = ["listening", "reading", "writing", "speaking"]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=2, choices=CEFR.choices, blank=True, default="")
    listening = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="+",
                                  limit_choices_to={"section": "listening"})
    reading = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="+",
                                limit_choices_to={"section": "reading"})
    writing = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="+",
                                limit_choices_to={"section": "writing"})
    speaking = models.ForeignKey(MockExam, on_delete=models.PROTECT, related_name="+",
                                 limit_choices_to={"section": "speaking"})
    is_published = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("exams:full_detail", args=[self.pk])

    def sections(self):
        """[(section, MockExam)] in exam order."""
        return [(s, getattr(self, s)) for s in self.SECTION_ORDER]

    @property
    def total_minutes(self):
        return sum(exam.time_limit for _, exam in self.sections())

    def publish_problems(self):
        problems = []
        for section, exam in self.sections():
            if exam.section != section:
                problems.append(f"The {section} slot must contain a {section} mock.")
            elif not exam.is_published:
                problems.append(f"Publish the {section} mock “{exam.title}” first.")
        return problems
