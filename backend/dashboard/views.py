from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from exams.models import Section
from results.models import ExamAttempt, FullMockAttempt
from speaking.models import SpeakingSubmission
from writing.models import WritingSubmission

from core.models import Word

from . import insights
from .services import student_stats


@login_required
def home(request):
    user = request.user
    if user.is_admin:
        return redirect("admin_dashboard:home")
    stats = student_stats(user)
    best = stats["best_multilevel"]
    return render(request, "dashboard/home.html", {
        "greeting": insights.greeting(),
        "stats": stats,
        "best": round(float(best)) if best is not None else None,
        "best_pct": round(float(best) * 100 / 75) if best is not None else 0,
        "best_level": insights.multilevel_to_cefr(float(best)) if best is not None else "",
        "platform": insights.platform_stats(),
        "activity": insights.activity(user),
        "curve": insights.learning_curve(user),
        "skills": insights.skill_levels(user),
        "library": insights.mock_library(),
        "sections": insights.section_cards(),
        "word": Word.of_the_day(),
        "full_last": FullMockAttempt.objects.filter(student=user, status=FullMockAttempt.Status.COMPLETED).first(),
        "continue_items": insights.continue_items(user),
    })


@login_required
def results(request):
    user = request.user
    qs = (ExamAttempt.objects.filter(student=user).exclude(status=ExamAttempt.Status.DISCARDED)
          .select_related("exam", "result").order_by("-started_at"))
    section = request.GET.get("section", "")
    if section == "full":
        fulls = (FullMockAttempt.objects.filter(student=user).select_related("full_mock")
                 .order_by("-started_at"))
        return render(request, "dashboard/results.html", {
            "section": "full", "sections": Section.choices, "full_page": Paginator(fulls, 15).get_page(
                request.GET.get("page")), "overview": insights.results_overview(user), "bars": [],
            "legend": []})
    if section not in Section.values:
        section = ""
    if section:
        qs = qs.filter(exam__section=section)
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    for attempt in page:
        attempt.parts_text = insights.attempt_parts(attempt)
        attempt.score75 = insights.score75(attempt) if attempt.status == ExamAttempt.Status.COMPLETED else None
        attempt.level = insights.multilevel_to_cefr(attempt.score75) if attempt.score75 is not None else ""
        attempt.meta = insights.SECTION_META[attempt.exam.section]
        attempt.pct = round(attempt.score75 * 100 / 75) if attempt.score75 is not None else 0
        attempt.raw = ""
        if attempt.practice and attempt.exam.is_objective and attempt.status == ExamAttempt.Status.COMPLETED:
            total = (attempt.correct_count or 0) + (attempt.incorrect_count or 0) + (attempt.unanswered_count or 0)
            attempt.raw = f"{attempt.correct_count or 0}/{total}"
            attempt.pct = round(float(attempt.percentage or 0))
        attempt.day = timezone.localtime(attempt.started_at).date()  # matches the list ordering
    today = timezone.localdate()
    return render(request, "dashboard/results.html", {
        "page": page, "section": section, "sections": Section.choices,
        "today": today, "yesterday": today - timedelta(days=1),
        "overview": insights.results_overview(user),
        "bars": insights.progression(user, section),
        "legend": [(label, insights.SECTION_META[k]["color"]) for k, label in Section.choices],
    })


@login_required
def writing_history(request):
    qs = (WritingSubmission.objects.filter(student=request.user)
          .select_related("task", "attempt__exam", "evaluation"))
    page = Paginator(qs, 10).get_page(request.GET.get("page"))
    for sub in page:
        ev = getattr(sub, "evaluation", None)
        sub.pct = round(float(sub.score) * 100 / 75) if sub.score is not None else 0
        sub.criteria = [(label, float(value), round(float(value) * 100 / 75)) for label, value in (
            ("Task", ev.task_score), ("Coherence", ev.coherence_score), ("Vocabulary", ev.vocabulary_score),
            ("Grammar", ev.grammar_score))] if ev else []
    summary = qs.aggregate(n=Count("id"), avg=Avg("score"), best=Max("score"),
                           words=Avg("word_count"))
    return render(request, "dashboard/writing_history.html", {"page": page, "summary": summary})


@login_required
def writing_detail(request, pk):
    sub = get_object_or_404(WritingSubmission.objects.select_related("task", "attempt__exam", "evaluation", "student"),
                            pk=pk)
    if sub.student_id != request.user.id and not request.user.is_admin:
        raise PermissionDenied
    return render(request, "dashboard/writing_detail.html", {"sub": sub, "ev": getattr(sub, "evaluation", None)})


@login_required
def speaking_history(request):
    """Recordings grouped by the attempt (sitting) they belong to."""
    subs = SpeakingSubmission.objects.select_related("question", "evaluation").order_by("question__part",
                                                                                      "question__order", "pk")
    attempts = (ExamAttempt.objects.filter(student=request.user, speaking_submissions__isnull=False)
                .exclude(status=ExamAttempt.Status.DISCARDED).distinct()
                .select_related("exam", "result").prefetch_related(Prefetch("speaking_submissions", queryset=subs))
                .order_by("-started_at"))
    page = Paginator(attempts, 6).get_page(request.GET.get("page"))
    for attempt in page:
        attempt.recs = list(attempt.speaking_submissions.all())
        attempt.score75 = insights.score75(attempt) if attempt.status == ExamAttempt.Status.COMPLETED else None
        attempt.pct = round(attempt.score75 * 100 / 75) if attempt.score75 is not None else 0
        attempt.level = insights.multilevel_to_cefr(attempt.score75) if attempt.score75 is not None else ""
        attempt.failed = sum(1 for r in attempt.recs if r.processing_status == "failed")
        attempt.seconds = sum(float(r.duration or 0) for r in attempt.recs)
    all_subs = SpeakingSubmission.objects.filter(student=request.user)
    summary = all_subs.aggregate(n=Count("id"), seconds=Max("duration"), avg=Avg("score"),
                                 done=Count("id", filter=Q(processing_status="completed")))
    summary["total_seconds"] = sum(float(d or 0) for d in all_subs.values_list("duration", flat=True))
    return render(request, "dashboard/speaking_history.html", {"page": page, "summary": summary})
