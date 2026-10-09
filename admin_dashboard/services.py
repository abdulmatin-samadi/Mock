"""Shared search/filter logic for admin submission and result listings."""
from datetime import date

from django.db.models import Q

from exams.models import Section
from results.models import ExamAttempt
from speaking.models import SpeakingStatus, SpeakingSubmission
from writing.models import ProcessingStatus, WritingSubmission


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _student_search(qs, q, prefix="student"):
    if not q:
        return qs
    return qs.filter(Q(**{f"{prefix}__first_name__icontains": q}) | Q(**{f"{prefix}__last_name__icontains": q})
                     | Q(**{f"{prefix}__email__icontains": q}))


def common_filters(params):
    return {
        "q": (params.get("q") or "").strip(),
        "date_from": _date(params.get("date_from")),
        "date_to": _date(params.get("date_to")),
        "min_score": _num(params.get("min_score")),
        "max_score": _num(params.get("max_score")),
        "status": params.get("status") or "",
    }


def filter_attempts(params):
    f = common_filters(params)
    f["section"] = params.get("section") if params.get("section") in Section.values else ""
    qs = ExamAttempt.objects.select_related("student", "exam", "result").order_by("-started_at")
    qs = _student_search(qs, f["q"])
    if f["section"]:
        qs = qs.filter(exam__section=f["section"])
    if f["status"] in ExamAttempt.Status.values:
        qs = qs.filter(status=f["status"])
    if f["date_from"]:
        qs = qs.filter(started_at__date__gte=f["date_from"])
    if f["date_to"]:
        qs = qs.filter(started_at__date__lte=f["date_to"])
    # Score filters use the normalised percentage (0–100) so every section compares.
    if f["min_score"] is not None:
        qs = qs.filter(percentage__gte=f["min_score"])
    if f["max_score"] is not None:
        qs = qs.filter(percentage__lte=f["max_score"])
    return qs, f


def filter_writing(params):
    f = common_filters(params)
    qs = (WritingSubmission.objects.select_related("student", "task", "attempt__exam", "evaluation")
          .order_by("-submitted_at"))
    qs = _student_search(qs, f["q"])
    if f["status"] in ProcessingStatus.values:
        qs = qs.filter(status=f["status"])
    if f["date_from"]:
        qs = qs.filter(submitted_at__date__gte=f["date_from"])
    if f["date_to"]:
        qs = qs.filter(submitted_at__date__lte=f["date_to"])
    if f["min_score"] is not None:
        qs = qs.filter(score__gte=f["min_score"])
    if f["max_score"] is not None:
        qs = qs.filter(score__lte=f["max_score"])
    return qs, f


def filter_speaking(params):
    f = common_filters(params)
    qs = (SpeakingSubmission.objects.select_related("student", "question", "exam", "evaluation")
          .order_by("-submitted_at"))
    qs = _student_search(qs, f["q"])
    if f["status"] in SpeakingStatus.values:
        qs = qs.filter(processing_status=f["status"])
    if f["date_from"]:
        qs = qs.filter(submitted_at__date__gte=f["date_from"])
    if f["date_to"]:
        qs = qs.filter(submitted_at__date__lte=f["date_to"])
    if f["min_score"] is not None:
        qs = qs.filter(score__gte=f["min_score"])
    if f["max_score"] is not None:
        qs = qs.filter(score__lte=f["max_score"])
    return qs, f
