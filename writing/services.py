import logging
import re

from django.db import transaction
from django.utils import timezone

from ai.exceptions import AIError
from ai.services import AIService
from ai.tasks import enqueue

from .models import ProcessingStatus, WritingEvaluation, WritingSubmission

logger = logging.getLogger(__name__)
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")

EVALUATION_FIELDS = [
    "provider", "model_name", "overall_score", "task_score", "coherence_score", "vocabulary_score",
    "grammar_score", "cefr_level", "task_feedback", "coherence_feedback", "vocabulary_feedback", "grammar_feedback",
    "detailed_feedback", "grammar_mistakes", "vocabulary_mistakes", "suggested_corrections", "weak_sentences",
    "strong_sentences", "improvement_suggestions", "raw_response",
]


def count_words(text):
    return len(WORD_RE.findall(text or ""))


def queue_evaluation(submission):
    enqueue(evaluate_submission, submission.pk)


def evaluate_submission(submission_id, service=None):
    """Background job: AI-evaluate one essay. Safe to call more than once."""
    from results.services import refresh_writing_attempt

    claimed = WritingSubmission.objects.filter(
        pk=submission_id, status__in=[ProcessingStatus.PENDING, ProcessingStatus.FAILED]
    ).update(status=ProcessingStatus.PROCESSING, error_message="")
    if not claimed:
        return
    sub = WritingSubmission.objects.select_related("task__exam").get(pk=submission_id)
    try:
        if sub.word_count == 0:
            data = AIService.empty_writing_result(sub.task)
        else:
            data = (service or AIService()).evaluate_writing(task=sub.task, essay=sub.essay, word_count=sub.word_count)
        with transaction.atomic():
            WritingEvaluation.objects.update_or_create(
                submission=sub, defaults={k: data[k] for k in EVALUATION_FIELDS})
            sub.status = ProcessingStatus.COMPLETED
            sub.score = data["overall_score"]
            sub.evaluated_at = timezone.now()
            sub.save(update_fields=["status", "score", "evaluated_at"])
    except AIError as e:
        logger.warning("Writing evaluation %s failed: %s", submission_id, e)
        WritingSubmission.objects.filter(pk=submission_id).update(
            status=ProcessingStatus.FAILED, error_message=str(e)[:1000], retries=sub.retries + 1)
    except Exception:
        logger.exception("Writing evaluation %s crashed", submission_id)
        WritingSubmission.objects.filter(pk=submission_id).update(
            status=ProcessingStatus.FAILED, error_message="Unexpected server error during evaluation.",
            retries=sub.retries + 1)
    finally:
        refresh_writing_attempt(sub.attempt_id)


def retry_evaluation(submission):
    """Admin action: re-run AI evaluation (e.g. after fixing the API key)."""
    from results.models import ExamAttempt

    WritingSubmission.objects.filter(pk=submission.pk).update(status=ProcessingStatus.PENDING, error_message="")
    ExamAttempt.objects.filter(pk=submission.attempt_id).update(status=ExamAttempt.Status.EVALUATING)
    with transaction.atomic():
        queue_evaluation(submission)
