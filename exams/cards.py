"""Data for the mock cards on section pages (#01, N/N READY, parts, attempt stats)."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import SpeakingQuestion

THEMES = {"listening": "teal", "reading": "amber", "writing": "violet", "speaking": "green"}


def _objective_items(exam):
    items = []
    for part in exam.parts.annotate(n=Count("questions")):
        ready = part.n > 0 and (exam.section != "listening" or bool(part.audio or exam.audio))
        items.append({"label": str(part.order), "title": part.summary or part.title, "ready": ready})
    return items


def _writing_items(exam):
    tasks = list(exam.writing_tasks.filter(is_published=True))
    part1 = [t for t in tasks if t.task_type in ("task1_1", "task1_2")]
    part2 = [t for t in tasks if t.task_type == "task2"]
    items = []
    if part1:
        items.append({"label": "PART 1", "title": exam.summary or "Letters", "ready": None,
                      "sub": [{"label": t.title.replace("Task ", "T"), "title": t.summary or t.get_task_type_display(),
                               "ready": bool(t.topic.strip())} for t in part1]})
    for t in part2:
        items.append({"label": "PART 2", "title": t.summary or t.topic[:60], "ready": bool(t.topic.strip())})
    return items


def _speaking_items(exam):
    by_part = {}
    for q in exam.speaking_questions.all():
        by_part.setdefault(q.part, []).append(q)
    items = []
    for part in SpeakingQuestion.Part.values:
        qs = by_part.get(part, [])
        title = next((q.summary for q in qs if q.summary), "") or (qs[0].question[:50] if qs else "Not added yet")
        items.append({"label": SpeakingQuestion.SHORT_LABELS[part].upper(), "title": title, "ready": bool(qs)})
    return items


def _ready_count(items):
    flat = []
    for item in items:
        flat += item.get("sub") or [item]
    return sum(1 for i in flat if i["ready"]), len(flat)


def mock_cards(exams, user=None, offset=0):
    exams = list(exams)
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    week = timezone.now() - timedelta(days=7)
    from results.models import ExamAttempt

    stats = {row["exam"]: row for row in ExamAttempt.objects.filter(exam__in=exams).values("exam").annotate(
        total=Count("id"), today=Count("id", filter=Q(started_at__gte=today)),
        week=Count("id", filter=Q(started_at__gte=week)))}
    trending = {pk for pk, _ in sorted(((pk, r["week"]) for pk, r in stats.items() if r["week"]),
                                       key=lambda x: -x[1])[:3]}
    mine = {}
    if user is not None and user.is_authenticated:
        for a in (ExamAttempt.objects.filter(student=user, exam__in=exams, practice="", full_mock_attempt__isnull=True)
                  .exclude(status=ExamAttempt.Status.DISCARDED).order_by("-started_at")):
            mine.setdefault(a.exam_id, a)

    cards = []
    for i, exam in enumerate(exams, start=1):
        if exam.is_objective:
            items = _objective_items(exam)
        elif exam.section == "writing":
            items = _writing_items(exam)
        else:
            items = _speaking_items(exam)
        ready, total = _ready_count(items)
        row = stats.get(exam.pk, {})
        cards.append({
            "exam": exam, "number": offset + i, "theme": THEMES[exam.section], "items": items,
            "ready": ready, "total": total, "all_ready": total and ready == total,
            "attempts": row.get("total", 0), "today": row.get("today", 0), "trending": exam.pk in trending,
            "mine": mine.get(exam.pk),
        })
    return cards
