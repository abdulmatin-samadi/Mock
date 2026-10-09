from django.db.models import Avg, Count, Max

from results.models import ExamAttempt
from speaking.models import SpeakingSubmission
from writing.models import WritingSubmission


def student_stats(user):
    """Aggregate statistics for one student (used by student + admin dashboards).
    Scores on different scales are compared through their server-computed percentage."""
    attempts = ExamAttempt.objects.filter(student=user)
    completed = attempts.filter(status=ExamAttempt.Status.COMPLETED)
    full = completed.filter(practice="")  # part practice never sets your best score or level
    agg = completed.aggregate(avg=Avg("percentage"), best=Max("percentage"))
    best_ml = full.aggregate(b=Max("result__scaled_score"))["b"]
    latest = full.exclude(result__cefr_level="").order_by("-completed_at").values_list(
        "result__cefr_level", flat=True).first()
    by_section = {row["exam__section"]: row for row in completed.values("exam__section").annotate(
        n=Count("id"), avg=Avg("percentage"), best=Max("percentage"))}
    return {
        "exams_completed": completed.count(),
        "exams_in_progress": attempts.filter(status=ExamAttempt.Status.IN_PROGRESS).count(),
        "average_percentage": agg["avg"],
        "best_percentage": agg["best"],
        "current_level": latest or "",
        "best_multilevel": best_ml,
        "writing_submissions": WritingSubmission.objects.filter(student=user).count(),
        "speaking_submissions": SpeakingSubmission.objects.filter(student=user).count(),
        "by_section": by_section,
    }
