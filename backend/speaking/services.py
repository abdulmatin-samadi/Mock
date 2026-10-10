import logging
import os

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ai.exceptions import AIError
from ai.services import AIService
from ai.tasks import enqueue
from core.validators import AUDIO_CONTENT_TYPES, validate_recording
from results.models import ExamAttempt

from .models import SpeakingEvaluation, SpeakingStatus, SpeakingSubmission

logger = logging.getLogger(__name__)

EVALUATION_FIELDS = [
    "provider", "model_name", "overall_score", "fluency_score", "vocabulary_score", "grammar_score",
    "pronunciation_score", "pronunciation_assessed", "cefr_level", "fluency_feedback", "coherence_feedback",
    "vocabulary_feedback", "grammar_feedback", "pronunciation_feedback", "detailed_feedback", "mistakes",
    "improvement_suggestions", "raw_response",
]


def can_access_recording(user, submission):
    """Only the student who recorded it and admins — never other students."""
    return user.is_authenticated and (submission.student_id == user.id or user.is_admin)


@transaction.atomic
def save_recording(*, user, attempt, question, audio, duration=0):
    attempt = ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt.pk)
    if attempt.student_id != user.id:
        raise PermissionDenied("This is not your attempt.")
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        raise ValidationError("This speaking test has already been submitted.")
    from results.services import attempt_speaking_questions

    if not attempt_speaking_questions(attempt).filter(pk=question.pk).exists():
        raise ValidationError("The question does not belong to this exam.")
    if SpeakingSubmission.objects.filter(attempt=attempt, question=question).exists():
        raise ValidationError("You have already submitted an answer for this question.")
    validate_recording(audio)
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0
    duration = max(0.0, min(duration, question.speaking_time + 30.0))
    ext = os.path.splitext(audio.name)[1].lower()
    try:
        sub = SpeakingSubmission.objects.create(
            attempt=attempt, student=user, exam=attempt.exam, question=question, audio_file=audio,
            mime_type=AUDIO_CONTENT_TYPES.get(ext, "application/octet-stream"), file_size=audio.size,
            duration=duration,
        )
    except IntegrityError:
        raise ValidationError("You have already submitted an answer for this question.")
    enqueue(process_submission, sub.pk)
    return sub


def process_submission(submission_id, service=None):
    """Background job: speech-to-text, then AI evaluation. Idempotent."""
    from results.services import refresh_speaking_attempt

    claimed = SpeakingSubmission.objects.filter(
        pk=submission_id, processing_status__in=[SpeakingStatus.PENDING, SpeakingStatus.FAILED]
    ).update(processing_status=SpeakingStatus.TRANSCRIBING, error_message="")
    if not claimed:
        return
    sub = SpeakingSubmission.objects.select_related("question__exam", "attempt__student").get(pk=submission_id)
    service = service or AIService()
    stt_meta = {}
    try:
        # 1-3. Speech-to-text, saved before evaluation so it survives evaluation errors.
        if not sub.transcript:
            result = service.transcribe_speaking(sub.audio_file)
            sub.transcript = result["text"]
            stt_meta = {"stt_provider": result["provider"], "stt_model": result["model"]}
            sub.save(update_fields=["transcript"])
        SpeakingSubmission.objects.filter(pk=sub.pk).update(processing_status=SpeakingStatus.EVALUATING)

        # 4-5. Evaluate the transcript.
        if not sub.transcript.strip():
            data = AIService.empty_speaking_result(sub.question)
        else:
            data = service.evaluate_speaking(question=sub.question, transcript=sub.transcript, duration=sub.duration,
                                             language=sub.attempt.student.feedback_language)

        # 6. Save.
        with transaction.atomic():
            defaults = {k: data[k] for k in EVALUATION_FIELDS}
            defaults.update(stt_meta)
            SpeakingEvaluation.objects.update_or_create(submission=sub, defaults=defaults)
            SpeakingSubmission.objects.filter(pk=sub.pk).update(
                processing_status=SpeakingStatus.COMPLETED, score=data["overall_score"], processed_at=timezone.now())
    except AIError as e:
        logger.warning("Speaking submission %s failed: %s", submission_id, e)
        SpeakingSubmission.objects.filter(pk=submission_id).update(
            processing_status=SpeakingStatus.FAILED, error_message=str(e)[:1000], retries=sub.retries + 1)
    except Exception:
        logger.exception("Speaking submission %s crashed", submission_id)
        SpeakingSubmission.objects.filter(pk=submission_id).update(
            processing_status=SpeakingStatus.FAILED, error_message="Unexpected server error while processing.",
            retries=sub.retries + 1)
    finally:
        refresh_speaking_attempt(sub.attempt_id)


def retry_processing(submission):
    SpeakingSubmission.objects.filter(pk=submission.pk).update(processing_status=SpeakingStatus.PENDING,
                                                               error_message="")
    ExamAttempt.objects.filter(pk=submission.attempt_id).exclude(
        status=ExamAttempt.Status.IN_PROGRESS).update(status=ExamAttempt.Status.EVALUATING)
    with transaction.atomic():
        enqueue(process_submission, submission.pk)
