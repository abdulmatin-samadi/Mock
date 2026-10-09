from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from exams.models import Section

from . import services
from .models import ExamAttempt, FullMockAttempt


@login_required
def attempt_detail(request, pk):
    """Full result page. Owner or admin only."""
    attempt = get_object_or_404(ExamAttempt.objects.select_related("exam", "student", "result"), pk=pk)
    if not services.can_view_attempt(request.user, attempt):
        raise PermissionDenied
    if attempt.status == ExamAttempt.Status.IN_PROGRESS and attempt.student_id == request.user.id:
        return redirect("exams:take", pk=attempt.pk)

    ctx = {"attempt": attempt, "exam": attempt.exam, "result": getattr(attempt, "result", None),
           "is_owner": attempt.student_id == request.user.id}
    section = attempt.exam.section
    if section in (Section.READING, Section.LISTENING):
        ctx["answers"] = (attempt.answers.select_related("question__part", "selected_option")
                          .prefetch_related("question__options").order_by("question__part__order", "question__order"))
        template = "results/detail_objective.html"
    elif section == Section.WRITING:
        ctx["submissions"] = attempt.writing_submissions.select_related("task", "evaluation").order_by("task__order")
        template = "results/detail_writing.html"
    else:
        ctx["submissions"] = attempt.speaking_submissions.select_related("question", "evaluation")
        template = "results/detail_speaking.html"
    return render(request, template, ctx)


@login_required
def full_detail(request, pk):
    """Overall result of a full Multilevel mock (owner or admin)."""
    full = get_object_or_404(FullMockAttempt.objects.select_related("full_mock", "student"), pk=pk)
    if full.student_id != request.user.id and not request.user.is_admin:
        raise PermissionDenied
    if full.student_id == request.user.id and full.status == FullMockAttempt.Status.IN_PROGRESS:
        return redirect("exams:full_progress", pk=full.pk)
    full = services.refresh_full_attempt(full.pk)
    sections = []
    for section, exam, attempt in services.full_progress(full):
        result = getattr(attempt, "result", None) if attempt else None
        score = result.scaled_score if result else None
        sections.append({"section": section, "exam": exam, "attempt": attempt, "score": score,
                         "level": result.cefr_level if result else "",
                         "pct": round(float(score) * 100 / 75) if score is not None else 0})
    return render(request, "results/full_detail.html", {
        "full": full, "sections": sections, "is_owner": full.student_id == request.user.id,
        "pct": round(float(full.score) * 100 / 75) if full.score is not None else 0})
