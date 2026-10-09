from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from speaking.models import SpeakingStatus, SpeakingSubmission
from speaking.services import process_submission
from writing.models import ProcessingStatus, WritingSubmission
from writing.services import evaluate_submission


class Command(BaseCommand):
    help = "Process pending AI writing evaluations and speaking transcriptions/evaluations."

    def add_arguments(self, parser):
        parser.add_argument("--retry-failed", action="store_true", help="Also retry failed items (max 3 tries).")
        parser.add_argument("--stuck-minutes", type=int, default=15,
                            help="Reset items stuck in processing for longer than this.")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(minutes=opts["stuck_minutes"])
        w_reset = WritingSubmission.objects.filter(status=ProcessingStatus.PROCESSING,
                                                   submitted_at__lt=cutoff).update(status=ProcessingStatus.PENDING)
        s_reset = SpeakingSubmission.objects.filter(
            processing_status__in=[SpeakingStatus.TRANSCRIBING, SpeakingStatus.EVALUATING], submitted_at__lt=cutoff
        ).update(processing_status=SpeakingStatus.PENDING)
        if w_reset or s_reset:
            self.stdout.write(f"Reset {w_reset} writing and {s_reset} speaking stuck items.")

        w_states = [ProcessingStatus.PENDING] + ([ProcessingStatus.FAILED] if opts["retry_failed"] else [])
        s_states = [SpeakingStatus.PENDING] + ([SpeakingStatus.FAILED] if opts["retry_failed"] else [])

        writing_ids = list(WritingSubmission.objects.filter(status__in=w_states, retries__lt=3)
                           .values_list("pk", flat=True)[: opts["limit"]])
        speaking_ids = list(SpeakingSubmission.objects.filter(processing_status__in=s_states, retries__lt=3)
                            .values_list("pk", flat=True)[: opts["limit"]])
        for pk in writing_ids:
            evaluate_submission(pk)
            self.stdout.write(f"writing #{pk}: {WritingSubmission.objects.get(pk=pk).status}")
        for pk in speaking_ids:
            process_submission(pk)
            self.stdout.write(f"speaking #{pk}: {SpeakingSubmission.objects.get(pk=pk).processing_status}")
        self.stdout.write(self.style.SUCCESS(f"Done: {len(writing_ids)} writing, {len(speaking_ids)} speaking."))
