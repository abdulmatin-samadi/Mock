from django.db import transaction

from .models import ExamPart, MockExam, Option, Question, SpeakingQuestion, WritingTask


def can_take_exam(user, exam):
    return user.is_authenticated and user.is_student and exam.is_published


def can_access_exam_media(user, exam):
    if not user.is_authenticated:
        return False
    return user.is_admin or (exam.is_published and user.is_student)


def validate_publishable(exam):
    """Return a list of problems that prevent publishing."""
    problems = []
    if exam.section in ("reading", "listening"):
        questions = Question.objects.filter(exam=exam).prefetch_related("options")
        if not questions:
            problems.append("Add at least one question.")
        for q in questions:
            if q.question_type == Question.Type.MULTIPLE_CHOICE and not any(o.is_correct for o in q.options.all()):
                problems.append(f"Question {q.order}: mark the correct option.")
            elif q.question_type in Question.LABEL_TYPES and not q.options.exists():
                problems.append(f"Question {q.order}: add matching options.")
            elif q.question_type != Question.Type.MULTIPLE_CHOICE and not q.correct_answer.strip():
                problems.append(f"Question {q.order}: set the correct answer.")
        if exam.section == "listening" and not exam.audio and not exam.parts.exclude(audio="").exists():
            problems.append("Upload the listening audio.")
        for part in exam.parts.filter(image="", questions__question_type=Question.Type.MAP_LABELLING).distinct():
            problems.append(f"{part.title}: upload the map picture for the map labelling questions.")
    elif exam.section == "writing":
        if not exam.writing_tasks.filter(is_published=True).exists():
            problems.append("Add at least one published writing task.")
    elif exam.section == "speaking":
        if not exam.speaking_questions.exists():
            problems.append("Add at least one speaking question.")
    return problems


def unanswered_questions(exam):
    """Reading/Listening questions that still have no correct answer (they block publishing)."""
    out = []
    for q in Question.objects.filter(exam=exam).select_related("part").prefetch_related("options"):
        opts = list(q.options.all())
        if q.question_type == Question.Type.MULTIPLE_CHOICE:
            if opts and not any(o.is_correct for o in opts):
                out.append(q)
        elif not q.correct_answer.strip() and (q.question_type not in Question.LABEL_TYPES or opts):
            out.append(q)
    return out


def set_correct_answer(question, value):
    """Set the answer from the mock page: an option id (multiple choice), a label, a TFNG choice or text."""
    q = question
    if q.question_type == Question.Type.MULTIPLE_CHOICE:
        opts = list(q.options.all())
        if not any(str(o.pk) == value for o in opts):
            return False
        for o in opts:
            o.is_correct = str(o.pk) == value
        Option.objects.bulk_update(opts, ["is_correct"])
        return True
    if q.fixed_choices:
        value = Question.canonical_choice(value)
        if value not in q.fixed_choices:
            return False
    elif q.question_type in Question.LABEL_TYPES:
        value = value.upper()
        if value not in {o.label.upper() for o in q.options.all()}:
            return False
    q.correct_answer = value[:500]
    q.save(update_fields=["correct_answer"])
    return True


@transaction.atomic
def duplicate_exam(exam, user=None):
    """Deep copy of a mock (unpublished). Audio/image files are shared, not copied."""
    copy = MockExam.objects.get(pk=exam.pk)
    copy.pk = None
    copy.title = f"{exam.title} (copy)"
    copy.is_published = False
    copy.created_by = user
    copy.save()

    for part in exam.parts.all():
        questions = list(part.questions.prefetch_related("options"))
        part.pk = None
        part.exam = copy
        part.save()
        for q in questions:
            options = list(q.options.all())
            q.pk = None
            q.part = part
            q.save()
            Option.objects.bulk_create([Option(question=q, label=o.label, text=o.text, is_correct=o.is_correct,
                                               order=o.order) for o in options])

    for task in WritingTask.objects.filter(exam=exam):
        task.pk = None
        task.exam = copy
        task.save()

    for sq in SpeakingQuestion.objects.filter(exam=exam):
        sq.pk = None
        sq.exam = copy
        sq.save()
    return copy


def next_part_order(exam):
    last = exam.parts.order_by("-order").first()
    return (last.order + 1) if last else 1


def next_question_number(exam):
    last = Question.objects.filter(exam=exam).order_by("-order").first()
    return (last.order + 1) if last else 1


def ensure_part(exam):
    part = exam.parts.first()
    if part is None:
        part = ExamPart.objects.create(exam=exam, title="Part 1", order=1)
    return part


def create_cefr_parts(exam):
    """Create the empty official Multilevel parts for a new Reading/Listening mock."""
    from . import cefr

    for preset in cefr.structure(exam.section):
        order = int(preset["code"][1:])
        if not exam.parts.filter(order=order).exists():
            ExamPart.objects.create(exam=exam, order=order, title=preset["title"], cefr_part=preset["code"],
                                    instructions=preset["instructions"])
