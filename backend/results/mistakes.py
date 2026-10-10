"""Mistakes notebook and AI answer explanations for Reading / Listening."""
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from exams import scoring
from exams.models import Question, Section

from .models import Answer, AnswerExplanation, ExamAttempt, LearnedMistake


class ExplanationLimit(Exception):
    pass


def mistakes(user, section=None):
    """Questions whose latest answer by this student was wrong or empty (newest first), minus learned ones.
    Returns a list of Answer objects (the latest answer to each question)."""
    answers = (Answer.objects
               .filter(attempt__student=user, attempt__status=ExamAttempt.Status.COMPLETED,
                       attempt__exam__section__in=[Section.READING, Section.LISTENING])
               .select_related("question__part__exam", "selected_option", "attempt")
               .prefetch_related("question__options")
               .order_by("-attempt__completed_at", "question__part__order", "question__order"))
    if section:
        answers = answers.filter(attempt__exam__section=section)
    learned = set(LearnedMistake.objects.filter(student=user).values_list("question_id", flat=True))
    seen, out = set(), []
    for a in answers[:2000]:
        if a.question_id in seen:
            continue
        seen.add(a.question_id)
        if not a.is_correct and a.question_id not in learned:
            out.append(a)
    return out


def gap_context(question, width=170):
    """The sentence around "(N) ______" in the part text, with the gap shown as "_____"."""
    text = question.part.passage or ""
    m = re.search(rf"\(\s*{question.order}\s*\)\s*_{{2,}}", text)
    if not m:
        return "", ""
    start, end = max(0, m.start() - width), min(len(text), m.end() + width)
    before = re.sub(r"\(\s*\d+\s*\)\s*_{2,}", "…", text[start:m.start()])
    after = re.sub(r"\(\s*\d+\s*\)\s*_{2,}", "…", text[m.end():end])
    return ("…" if start else "") + " ".join(before.split()), " ".join(after.split()) + ("…" if end < len(text) else "")


def can_see_answer(user, question):
    """Explanations and checks reveal the answer: only after the student has finished an attempt with it."""
    if user.is_admin:
        return True
    return Answer.objects.filter(question=question, attempt__student=user,
                                 attempt__status=ExamAttempt.Status.COMPLETED).exists()


def check(question, value):
    """Grade a retry without saving anything."""
    option_id = None
    if question.question_type == Question.Type.MULTIPLE_CHOICE:
        try:
            option_id = int(value)
        except (TypeError, ValueError):
            option_id = None
    return bool(str(value or "").strip()) and scoring.check_answer(question, str(value or ""), option_id)


def explanation(user, question, language):
    """Cached AI explanation (shared by all students). Raises ExplanationLimit or ai.exceptions.AIError."""
    language = language if language in ("uz", "en") else user.feedback_language
    found = AnswerExplanation.objects.filter(question=question, language=language).first()
    if found:
        return found.text
    key = f"explain:{user.pk}:{timezone.localdate():%Y%m%d}"
    used = cache.get(key, 0)
    if used >= settings.AI_EXPLAIN_DAILY_LIMIT and not user.is_admin:
        raise ExplanationLimit
    from ai.services import AIService

    text = AIService().explain_answer(question=question, language=language)
    cache.set(key, used + 1, 60 * 60 * 24)
    obj, _ = AnswerExplanation.objects.get_or_create(question=question, language=language,
                                                     defaults={"text": text})
    return obj.text
