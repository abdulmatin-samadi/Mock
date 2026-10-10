"""Attempt lifecycle and all scoring. Nothing here trusts client-side scores:
clients send raw answers / essays / recordings; correctness, scores, bands and
CEFR levels are computed on the server."""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext, ngettext

from exams import scoring
from exams.models import MockExam, Question, Section
from exams.services import can_take_exam

from .models import Answer, ExamAttempt, FullMockAttempt, Result

MAX_ESSAY_CHARS = 20000


# ---------------------------------------------------------------- helpers
def can_view_attempt(user, attempt):
    return user.is_authenticated and (attempt.student_id == user.id or user.is_admin)


def deadline(attempt):
    minutes = attempt.time_limit or attempt.exam.time_limit
    if not minutes:
        return None
    return attempt.started_at + timedelta(minutes=minutes)


# ------------------------------------------------------ part practice scope
def practice_options(exam):
    """Parts a student can practise on their own (the "Part Practice" mode)."""
    from math import ceil

    from django.db.models import Count

    options = []
    if exam.is_objective:
        parts = list(exam.parts.annotate(n=Count("questions")).filter(n__gt=0))
        total = sum(p.n for p in parts) or 1
        for i, p in enumerate(parts, start=1):
            minutes = max(5, round(exam.time_limit * p.n / total)) if exam.time_limit else None
            options.append({"key": f"part:{p.pk}", "badge": str(i), "title": p.title,
                            "sub": ngettext("%(n)d question", "%(n)d questions", p.n) % {"n": p.n},
                            "minutes": minutes})
    elif exam.section == Section.WRITING:
        for t in exam.writing_tasks.filter(is_published=True):
            words = f"{t.minimum_word_count}–{t.maximum_word_count}" if t.maximum_word_count else f"{t.minimum_word_count}+"
            kind = t.get_task_type_display().split("—")[-1].strip()
            options.append({"key": f"task:{t.pk}", "badge": t.title.replace("Task", "").strip() or str(t.order),
                            "title": t.title, "sub": f"{kind} • {words} " + gettext("words"), "minutes": t.time_limit})
    else:
        from exams.models import SpeakingQuestion

        by_part = {}
        for q in exam.speaking_questions.all():
            by_part.setdefault(q.part, []).append(q)
        for part, qs in sorted(by_part.items()):
            seconds = sum(q.preparation_time + q.speaking_time for q in qs)
            label = SpeakingQuestion.SHORT_LABELS.get(part, f"Part {part}")
            options.append({"key": f"part:{part}", "badge": label.replace("Part", "").strip(), "title": label,
                            "sub": f"{SpeakingQuestion.Part(part).label.split('—')[-1].strip()} • "
                                   + ngettext("%(n)d question", "%(n)d questions", len(qs)) % {"n": len(qs)},
                            "minutes": ceil(seconds / 60) + 2})
    return options


def _practice_value(attempt):
    return attempt.practice.partition(":")[2] if attempt.practice else ""


def attempt_questions(attempt):
    qs = Question.objects.filter(exam=attempt.exam)
    return qs.filter(part_id=_practice_value(attempt)) if attempt.practice else qs


def attempt_tasks(attempt):
    qs = attempt.exam.writing_tasks.filter(is_published=True)
    return qs.filter(pk=_practice_value(attempt)) if attempt.practice else qs


def attempt_speaking_questions(attempt):
    qs = attempt.exam.speaking_questions.all()
    return qs.filter(part=_practice_value(attempt)) if attempt.practice else qs


def past_grace(attempt, now=None):
    dl = deadline(attempt)
    if dl is None:
        return False
    return (now or timezone.now()) > dl + timedelta(seconds=settings.EXAM_SUBMIT_GRACE_SECONDS)


def _q2(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _lock(attempt):
    return ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt.pk)


def _propagates(fn):
    """After a section attempt changes state, refresh its parent full mock (if any)."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        attempt = out[0] if isinstance(out, tuple) else out
        if attempt is not None and attempt.full_mock_attempt_id:
            refresh_full_attempt(attempt.full_mock_attempt_id)
        return out

    return wrapper


# ---------------------------------------------------------------- start
@transaction.atomic
def start_attempt(user, exam: MockExam, full_attempt=None, practice=""):
    """Start (or resume) the full section test, or — with `practice` — a single part."""
    if not can_take_exam(user, exam):
        raise PermissionDenied("Only students can take published mock exams.")
    time_limit = None
    if practice:
        option = next((o for o in practice_options(exam) if o["key"] == practice), None)
        if option is None or full_attempt is not None:
            raise ValidationError("This part cannot be practised separately.")
        time_limit = option["minutes"]
    attempt = (ExamAttempt.objects.select_for_update()
               .filter(student=user, exam=exam, status=ExamAttempt.Status.IN_PROGRESS,
                       full_mock_attempt=full_attempt, practice=practice).first())
    if attempt and exam.is_objective and past_grace(attempt):
        grade_objective(attempt, late=True)  # time is over: grade what was autosaved
        attempt = None
    if attempt:
        return attempt, False
    from accounts.guest import check_can_start

    check_can_start(user)  # guests get one free mock
    return ExamAttempt.objects.create(student=user, exam=exam, full_mock_attempt=full_attempt, practice=practice,
                                      time_limit=time_limit), True


# ------------------------------------------------- reading / listening
def _normalise_answer(question, value):
    """Returns (text, option) for storage. Invalid option ids are dropped."""
    if value is None:
        return "", None
    if question.question_type == Question.Type.MULTIPLE_CHOICE:
        try:
            option = next((o for o in question.options.all() if o.pk == int(value)), None)
        except (TypeError, ValueError):
            option = None
        return (option.label if option else ""), option
    text = str(value).strip()[:500]
    if question.question_type in Question.LABEL_TYPES:
        labels = {o.label.upper() for o in question.options.all()}
        return (text.upper() if text.upper() in labels else ""), None
    if question.fixed_choices:
        choice = Question.canonical_choice(text)
        return (choice if choice in question.fixed_choices else ""), None
    return text, None


@transaction.atomic
def save_answers(attempt, answers: dict):
    """Autosave raw answers while the attempt is open. No grading happens here."""
    attempt = _lock(attempt)
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt has already been submitted.")
    if not attempt.exam.is_objective:
        raise ValidationError("Answers can only be saved for Reading and Listening exams.")
    if past_grace(attempt):
        raise ValidationError("Time is over — answers can no longer be changed.")
    if not isinstance(answers, dict):
        raise ValidationError("Answers must be an object keyed by question id.")
    questions = {q.pk: q for q in attempt_questions(attempt).prefetch_related("options")}
    saved = 0
    for key, value in answers.items():
        try:
            q = questions.get(int(key))
        except (TypeError, ValueError):
            q = None
        if q is None:
            continue
        text, option = _normalise_answer(q, value)
        Answer.objects.update_or_create(attempt=attempt, question=q,
                                        defaults={"answer": text, "selected_option": option})
        saved += 1
    return saved


@_propagates
@transaction.atomic
def grade_objective(attempt, late=False):
    attempt = _lock(attempt)
    exam = attempt.exam
    questions = list(attempt_questions(attempt).select_related("part").prefetch_related("options"))
    existing = {a.question_id: a for a in Answer.objects.filter(attempt=attempt)}
    score = Decimal(0)
    max_score = Decimal(0)
    correct = incorrect = unanswered = 0
    per_part = {}
    for q in questions:
        max_score += q.points
        ans = existing.get(q.pk) or Answer(attempt=attempt, question=q)
        answered = bool(ans.answer or ans.selected_option_id)
        ok = answered and scoring.check_answer(q, ans.answer, ans.selected_option_id)
        ans.is_correct = ok
        ans.points = q.points if ok else Decimal(0)
        ans.save()
        score += ans.points
        if ok:
            correct += 1
        elif answered:
            incorrect += 1
        else:
            unanswered += 1
        part = per_part.setdefault(q.part.title, {"correct": 0, "total": 0})
        part["total"] += 1
        part["correct"] += int(ok)

    now = timezone.now()
    pct = (score * 100 / max_score) if max_score else Decimal(0)
    attempt.score = _q2(score)
    attempt.max_score = _q2(max_score)
    attempt.percentage = _q2(pct)
    attempt.correct_count, attempt.incorrect_count, attempt.unanswered_count = correct, incorrect, unanswered
    attempt.submitted_at = attempt.submitted_at or now
    attempt.completed_at = now
    attempt.time_spent = int((attempt.submitted_at - attempt.started_at).total_seconds())
    attempt.is_late = late
    attempt.status = ExamAttempt.Status.COMPLETED
    attempt.save()

    if attempt.practice:
        # One part is not a whole test: no 0–75 score or CEFR level, just the part's result.
        scaled, cefr = None, ""
        feedback = (f"Part practice: {correct} of {len(questions)} correct ({pct:.0f}%). "
                    "Take the full test to get a Multilevel score (0–75) and CEFR level.")
    else:
        scaled = Decimal(scoring.percentage_to_multilevel(pct))
        cefr = scoring.multilevel_to_cefr(scaled)
        feedback = f"{correct} of {len(questions)} correct — Multilevel score {scaled:g}/75 ({cefr})."
    if late:
        feedback += " Submitted after the time limit: only answers saved before the deadline were graded."
    Result.objects.update_or_create(attempt=attempt, defaults={
        "score": attempt.score, "scaled_score": scaled, "cefr_level": cefr, "feedback": feedback,
        "details": {"parts": per_part, "correct": correct, "incorrect": incorrect, "unanswered": unanswered,
                    "raw_score": float(score), "max_score": float(max_score)},
    })
    return attempt


@transaction.atomic
def submit_objective(attempt, answers=None):
    attempt = _lock(attempt)
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt has already been submitted.")
    late = past_grace(attempt)
    if answers and not late:
        save_answers(attempt, answers)
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["submitted_at"])
    return grade_objective(attempt, late=late)


# -------------------------------------------------------------- writing
@transaction.atomic
def save_drafts(attempt, drafts):
    """Server-side autosave of unsubmitted essays, so a writing mock can be resumed on any device."""
    attempt = _lock(attempt)
    if attempt.status != ExamAttempt.Status.IN_PROGRESS or attempt.exam.section != Section.WRITING:
        raise ValidationError("Drafts can only be saved for a writing test in progress.")
    if not isinstance(drafts, dict):
        raise ValidationError("Drafts must be an object keyed by task id.")
    allowed = {str(pk) for pk in attempt_tasks(attempt).values_list("pk", flat=True)}
    clean = {k: str(v)[:MAX_ESSAY_CHARS] for k, v in drafts.items() if str(k) in allowed}
    attempt.drafts = {**attempt.drafts, **clean}
    attempt.drafts_saved_at = timezone.now()
    attempt.save(update_fields=["drafts", "drafts_saved_at"])
    return len(clean)


@transaction.atomic
def submit_writing(attempt, essays: dict):
    from writing.models import WritingSubmission
    from writing.services import count_words, queue_evaluation

    attempt = _lock(attempt)
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt has already been submitted.")
    if not isinstance(essays, dict):
        raise ValidationError("Essays must be an object keyed by task id.")
    tasks = list(attempt_tasks(attempt))
    texts = {}
    for task in tasks:
        text = str(essays.get(str(task.pk), essays.get(task.pk, "")) or "").replace("\r\n", "\n").strip()
        if len(text) > MAX_ESSAY_CHARS:
            raise ValidationError(f"“{task.title}” is too long (max {MAX_ESSAY_CHARS} characters).")
        texts[task.pk] = text
    if not any(texts.values()):
        raise ValidationError("Write at least one response before submitting.")

    now = timezone.now()
    attempt.submitted_at = now
    attempt.time_spent = int((now - attempt.started_at).total_seconds())
    attempt.is_late = past_grace(attempt, now)
    attempt.status = ExamAttempt.Status.EVALUATING
    attempt.save()

    submissions = []
    for task in tasks:
        sub = WritingSubmission.objects.create(attempt=attempt, student=attempt.student, task=task,
                                               essay=texts[task.pk], word_count=count_words(texts[task.pk]))
        queue_evaluation(sub)
        submissions.append(sub)
    return attempt, submissions


@_propagates
@transaction.atomic
def refresh_writing_attempt(attempt_id):
    """Aggregate task evaluations into the attempt result once all are done."""
    from writing.models import ProcessingStatus

    attempt = ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
    if attempt.status == ExamAttempt.Status.IN_PROGRESS:
        return attempt
    subs = list(attempt.writing_submissions.select_related("task", "evaluation"))
    statuses = {s.status for s in subs}
    if statuses & {ProcessingStatus.PENDING, ProcessingStatus.PROCESSING}:
        attempt.status = ExamAttempt.Status.EVALUATING
        attempt.save(update_fields=["status"])
        return attempt
    if ProcessingStatus.FAILED in statuses:
        attempt.status = ExamAttempt.Status.FAILED
        attempt.save(update_fields=["status"])
        return attempt

    overall = scoring.round_score(mean(float(s.evaluation.overall_score) for s in subs))
    cefr = scoring.multilevel_to_cefr(overall)

    attempt.score = overall
    attempt.max_score = scoring.MAX_SCORE
    attempt.percentage = _q2(overall * 100 / scoring.MAX_SCORE)
    attempt.status = ExamAttempt.Status.COMPLETED
    attempt.completed_at = timezone.now()
    attempt.save()
    Result.objects.update_or_create(attempt=attempt, defaults={
        "score": overall, "scaled_score": overall, "cefr_level": cefr,
        "feedback": " ".join(f"{s.task.title}: {s.evaluation.overall_score:g}/75." for s in subs),
        "details": {"tasks": [{"task": s.task.title, "score": float(s.evaluation.overall_score),
                               "word_count": s.word_count} for s in subs]},
    })
    return attempt


# ------------------------------------------------------------- speaking
@transaction.atomic
def submit_speaking(attempt):
    attempt = _lock(attempt)
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt has already been submitted.")
    if not attempt.speaking_submissions.exists():
        raise ValidationError("Record at least one answer before finishing the test.")
    now = timezone.now()
    attempt.submitted_at = now
    attempt.time_spent = int((now - attempt.started_at).total_seconds())
    attempt.status = ExamAttempt.Status.EVALUATING
    attempt.save()
    transaction.on_commit(lambda: refresh_speaking_attempt(attempt.pk))
    return attempt


def _speaking_parts(subs):
    """Mean 0–75 score per Multilevel speaking part, in exam order."""
    from exams.models import SpeakingQuestion

    by_part = {}
    for s in subs:
        by_part.setdefault(s.question.part, []).append(float(s.evaluation.overall_score))
    return [{"part": SpeakingQuestion.SHORT_LABELS.get(p, f"Part {p}"), "score": round(mean(v)), "answers": len(v)}
            for p, v in sorted(by_part.items())]


@_propagates
@transaction.atomic
def refresh_speaking_attempt(attempt_id):
    from speaking.models import SpeakingStatus

    attempt = ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
    if attempt.status == ExamAttempt.Status.IN_PROGRESS:
        return attempt  # still recording; finalised on submit
    subs = list(attempt.speaking_submissions.select_related("question", "evaluation"))
    statuses = {s.processing_status for s in subs}
    if statuses - {SpeakingStatus.COMPLETED, SpeakingStatus.FAILED}:
        attempt.status = ExamAttempt.Status.EVALUATING
        attempt.save(update_fields=["status"])
        return attempt
    if SpeakingStatus.FAILED in statuses:
        attempt.status = ExamAttempt.Status.FAILED
        attempt.save(update_fields=["status"])
        return attempt

    exam = attempt.exam
    evals = [s.evaluation for s in subs]
    crit = {
        "fluency": int(scoring.round_score(mean(float(e.fluency_score) for e in evals))),
        "vocabulary": int(scoring.round_score(mean(float(e.vocabulary_score) for e in evals))),
        "grammar": int(scoring.round_score(mean(float(e.grammar_score) for e in evals))),
    }
    overall = scoring.round_score(mean(crit.values()))
    cefr = scoring.multilevel_to_cefr(overall)

    total_questions = attempt_speaking_questions(attempt).count()
    missing = total_questions - len(subs)
    attempt.score = overall
    attempt.max_score = scoring.MAX_SCORE
    attempt.percentage = _q2(overall * 100 / scoring.MAX_SCORE)
    attempt.status = ExamAttempt.Status.COMPLETED
    attempt.completed_at = timezone.now()
    attempt.unanswered_count = max(0, missing)
    attempt.save()
    feedback = (f"Overall {overall:g}/75 from {len(subs)} recorded answer(s). Pronunciation was not part of the "
                f"score (transcript-based evaluation).")
    if missing > 0:
        feedback += f" {missing} question(s) were not answered."
    Result.objects.update_or_create(attempt=attempt, defaults={
        "score": overall, "scaled_score": overall, "cefr_level": cefr, "feedback": feedback,
        "details": {"criteria": crit, "parts": _speaking_parts(subs), "answered": len(subs), "questions": total_questions,
                    "pronunciation_assessed": any(e.pronunciation_assessed for e in evals)},
    })
    return attempt


# ------------------------------------------------------------ dispatcher
def submit_attempt(attempt, payload):
    section = attempt.exam.section
    if section in (Section.READING, Section.LISTENING):
        return submit_objective(attempt, (payload or {}).get("answers") or {})
    if section == Section.WRITING:
        attempt, _ = submit_writing(attempt, (payload or {}).get("essays") or {})
        return attempt
    if section == Section.SPEAKING:
        return submit_speaking(attempt)
    raise ValidationError("Unknown section.")


# ------------------------------------------------------------ full mock
def can_take_full_mock(user, full_mock):
    return user.is_authenticated and user.is_student and full_mock.is_published


@transaction.atomic
def start_full_mock(user, full_mock):
    """Resume the student's unfinished sitting or start a new one."""
    if not can_take_full_mock(user, full_mock):
        raise PermissionDenied("Only students can take published full mocks.")
    if getattr(user, "is_guest", False):
        from accounts.guest import GuestLimitReached

        raise GuestLimitReached  # full mocks need an account
    full = (FullMockAttempt.objects.select_for_update()
            .filter(student=user, full_mock=full_mock, status=FullMockAttempt.Status.IN_PROGRESS).first())
    if full:
        return full, False
    return FullMockAttempt.objects.create(student=user, full_mock=full_mock), True


def full_progress(full):
    """[(section, MockExam, ExamAttempt|None)] in exam order."""
    return [(section, exam, full.section_attempt(section)) for section, exam in full.full_mock.sections()]


def next_section(full):
    """First section that has not been submitted yet, or None when all four are done."""
    for section, exam, attempt in full_progress(full):
        if attempt is None or attempt.status == ExamAttempt.Status.IN_PROGRESS:
            return section, exam, attempt
    return None


@transaction.atomic
def start_next_section(full):
    nxt = next_section(full)
    if nxt is None:
        raise ValidationError("All sections of this full mock have been submitted.")
    section, exam, attempt = nxt
    if attempt is not None:
        return attempt
    attempt, _ = start_attempt(full.student, exam, full_attempt=full)
    return attempt


@transaction.atomic
def refresh_full_attempt(full_id):
    """Overall Multilevel score = mean of the four section scores (0–75), once all are completed."""
    full = FullMockAttempt.objects.select_for_update().select_related("full_mock").get(pk=full_id)
    rows = full_progress(full)
    attempts = [a for _, _, a in rows]
    if any(a is None or a.status == ExamAttempt.Status.IN_PROGRESS for a in attempts):
        status = FullMockAttempt.Status.IN_PROGRESS
    elif any(a.status == ExamAttempt.Status.FAILED for a in attempts):
        status = FullMockAttempt.Status.FAILED
    elif any(a.status == ExamAttempt.Status.EVALUATING for a in attempts):
        status = FullMockAttempt.Status.EVALUATING
    else:
        status = FullMockAttempt.Status.COMPLETED

    if status == FullMockAttempt.Status.COMPLETED and full.status != status:
        scores = {}
        for section, _, attempt in rows:
            result = getattr(attempt, "result", None)
            scores[section] = float(result.scaled_score) if result and result.scaled_score is not None else 0.0
        overall = scoring.round_score(mean(scores.values()))
        full.score = overall
        full.cefr_level = scoring.multilevel_to_cefr(overall)
        full.completed_at = timezone.now()
        full.details = {"sections": scores}
    full.status = status
    full.save()
    return full
