from django import forms
from django.contrib.auth import password_validation
from django.forms import inlineformset_factory

from accounts.models import User
from exams.models import ExamPart, FullMock, MockExam, Option, Question, SpeakingQuestion, WritingTask

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class AdminUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, strip=False,
                               help_text="Required for new users. Leave empty to keep the current password.")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active", "phone_number", "profile_photo"]

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        if not self.instance.pk:
            self.fields["password"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account uses this email.")
        return email

    def clean(self):
        data = super().clean()
        if self.instance.pk and self.acting_user and self.instance.pk == self.acting_user.pk:
            if data.get("role") != User.Role.ADMIN or not data.get("is_active"):
                raise forms.ValidationError("You cannot remove your own admin role or deactivate yourself.")
        pw = data.get("password")
        if pw:
            password_validation.validate_password(pw, self.instance)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        if user.role != User.Role.ADMIN:
            user.is_superuser = False
        if commit:
            user.save()
        return user


class MockExamForm(forms.ModelForm):
    cefr_layout = forms.BooleanField(
        required=False, initial=True, label="Lay out the official CEFR parts",
        help_text="Creates Part 1–5 (Reading) or Part 1–6 (Listening) with their instructions, ready for questions.")

    class Meta:
        model = MockExam
        fields = ["title", "summary", "level", "time_limit", "description", "instructions", "audio", "transcript"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "instructions": forms.Textarea(attrs={"rows": 3}),
                   "transcript": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, section=None, **kwargs):
        super().__init__(*args, **kwargs)
        section = section or self.instance.section
        if self.instance.pk or section not in ("reading", "listening"):
            del self.fields["cefr_layout"]
        if section != "listening":
            del self.fields["audio"]
            del self.fields["transcript"]
        else:
            self.fields["audio"].help_text = "Main recording (mp3/m4a/wav/ogg). Sections can also have their own audio."


class ExamPartForm(forms.ModelForm):
    class Meta:
        model = ExamPart
        fields = ["cefr_part", "title", "summary", "order", "instructions", "passage", "image", "audio", "transcript"]
        widgets = {"instructions": forms.Textarea(attrs={"rows": 2}), "passage": forms.Textarea(attrs={"rows": 14}),
                   "transcript": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, section=None, **kwargs):
        from exams import cefr

        super().__init__(*args, **kwargs)
        presets = cefr.structure(section)
        self.fields["cefr_part"] = forms.ChoiceField(
            label="CEFR part", required=False,
            choices=[("", "Custom part")] + [(p["code"], f"{p['title']} — usually {p['count']} questions")
                                             for p in presets],
            help_text="Sets which question types this part accepts.")
        self.fields["passage"].help_text = (
            "Text of the part. For gap filling, write each gap as (N) ______ where N is the question number — "
            "the gap appears as an answer box inside the text.")
        if section == "reading":
            del self.fields["audio"]
            del self.fields["transcript"]
            self.fields["image"].help_text = "Optional picture or diagram"
        else:
            self.fields["passage"].label = "Notes / text (optional)"
            self.fields["image"].help_text = "Map or plan for map-labelling questions"


class ExamQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["order", "question_type", "prompt", "correct_answer", "points", "explanation"]
        widgets = {"prompt": forms.Textarea(attrs={"rows": 3}), "explanation": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, part=None, **kwargs):
        from exams import cefr

        super().__init__(*args, **kwargs)
        allowed = cefr.allowed_types(part) if part is not None else None
        if allowed:
            labels = dict(Question.Type.choices)
            current = self.instance.question_type if self.instance.pk else None
            types = allowed + ([current] if current and current not in allowed else [])
            self.fields["question_type"].choices = [(t, labels[t]) for t in types]
            if not self.instance.pk:
                self.initial.setdefault("question_type", allowed[0])


class BaseExamOptionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        qtype = getattr(self, "question_type", None)
        correct_answer = (getattr(self, "correct_answer", "") or "").strip().upper()
        options = [f.cleaned_data for f in self.forms
                   if f.cleaned_data and not f.cleaned_data.get("DELETE")
                   and (f.cleaned_data.get("text") or f.cleaned_data.get("label"))]
        labels = [o["label"].strip().upper() for o in options]
        if len(labels) != len(set(labels)):
            raise forms.ValidationError("Option labels must be unique.")
        if qtype == Question.Type.MULTIPLE_CHOICE:
            if len(options) < 2:
                raise forms.ValidationError("Multiple choice questions need at least two options.")
            if not any(o.get("is_correct") for o in options):
                raise forms.ValidationError("Mark the correct option.")
        elif qtype in Question.LABEL_TYPES:
            if len(options) < 2:
                raise forms.ValidationError("Matching questions need the list of options (A, B, C…).")
            if correct_answer not in labels:
                raise forms.ValidationError("The correct answer must be one of the option labels.")


ExamOptionFormSet = inlineformset_factory(
    Question, Option, formset=BaseExamOptionFormSet, fields=["label", "text", "is_correct", "order"],
    extra=4, can_delete=True, max_num=20,
)


def validate_question_answer(form):
    """Cross-field checks that depend on question type."""
    qtype = form.cleaned_data.get("question_type")
    answer = (form.cleaned_data.get("correct_answer") or "").strip()
    if qtype in Question.FIXED_CHOICES:
        choice = Question.canonical_choice(answer)
        if choice not in Question.FIXED_CHOICES[qtype]:
            form.add_error("correct_answer", f"Use one of: {', '.join(Question.FIXED_CHOICES[qtype])}.")
        else:
            form.cleaned_data["correct_answer"] = choice
            form.instance.correct_answer = choice
    elif qtype in Question.TEXT_TYPES:
        if not answer:
            form.add_error("correct_answer", "Enter the accepted answer(s), separated by |.")
    elif qtype in Question.LABEL_TYPES:
        form.instance.correct_answer = answer.upper()
    return form.is_valid()


class WritingTaskForm(forms.ModelForm):
    class Meta:
        model = WritingTask
        fields = ["order", "title", "task_type", "summary", "topic", "instructions", "image", "minimum_word_count", "maximum_word_count", "time_limit",
                  "level", "is_published"]
        widgets = {"topic": forms.Textarea(attrs={"rows": 4}), "instructions": forms.Textarea(attrs={"rows": 3})}


class SpeakingQuestionForm(forms.ModelForm):
    class Meta:
        model = SpeakingQuestion
        fields = ["part", "order", "question", "summary", "image", "cue_card_points", "preparation_time", "speaking_time"]
        widgets = {"question": forms.Textarea(attrs={"rows": 2}), "cue_card_points": forms.Textarea(attrs={"rows": 4})}


class FullMockForm(forms.ModelForm):
    class Meta:
        model = FullMock
        fields = ["title", "level", "description", "listening", "reading", "writing", "speaking"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"listening": "Section 1", "reading": "Section 2", "writing": "Section 3", "speaking": "Section 4"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for section in FullMock.SECTION_ORDER:
            self.fields[section].queryset = MockExam.objects.filter(section=section).order_by("-created_at")
            self.fields[section].label_from_instance = (
                lambda e: f"{e.title}{'' if e.is_published else ' (draft)'}")
