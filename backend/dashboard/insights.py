"""Data for the student home dashboard and the results page.

Every number comes from the database (attempts, results, mocks, courses). Charts
are pre-computed here so templates only render them (inline SVG / CSS bars).
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from exams.models import MockExam, Section
from exams.scoring import MAX_SCORE, multilevel_to_cefr
from results import services as attempt_services
from results.models import ExamAttempt
from speaking.models import SpeakingEvaluation
from writing.models import WritingEvaluation

SECTION_META = {
    "listening": {"icon": "headphones", "color": "#3b82f6"},
    "reading": {"icon": "book", "color": "#f59e0b"},
    "writing": {"icon": "pen", "color": "#8b5cf6"},
    "speaking": {"icon": "mic", "color": "#10b981"},
}
DAY_HOURS = range(6, 18)  # 06:00–17:59 local time counts as "day"


def _start_of_today():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def score75(attempt):
    """0–75 score of a completed attempt (falls back to percentage for legacy rows)."""
    if attempt.practice and attempt.exam.is_objective:
        return None  # a single part has no 0–75 score
    result = getattr(attempt, "result", None)
    if result is not None and result.scaled_score is not None:
        return float(result.scaled_score)
    if attempt.percentage is not None:
        return float(attempt.percentage) * float(MAX_SCORE) / 100
    return None


# ------------------------------------------------------------ platform-wide
def platform_stats():
    today = _start_of_today()
    return {
        "attempts_all_time": ExamAttempt.objects.count(),
        "attempts_today": ExamAttempt.objects.filter(started_at__gte=today).count(),
        "new_mocks_week": MockExam.objects.published().filter(
            created_at__gte=timezone.now() - timedelta(days=7)).count(),
    }


def section_cards():
    today = _start_of_today()
    mocks = dict(MockExam.objects.published().values_list("section").annotate(n=Count("id")))
    attempts = {row["exam__section"]: row for row in ExamAttempt.objects.values("exam__section").annotate(
        total=Count("id"), today=Count("id", filter=Q(started_at__gte=today)))}
    cards = []
    labels = dict(Section.choices)
    for key in ("speaking", "writing", "listening", "reading"):
        label = labels[key]
        row = attempts.get(key, {})
        cards.append({"key": key, "label": label, **SECTION_META[key], "mocks": mocks.get(key, 0),
                      "today": row.get("today", 0), "total": row.get("total", 0)})
    return cards


def continue_items(user):
    """Unfinished attempts, most recently active first (the "Continue where you left off" banner)."""
    from django.urls import reverse

    items = []
    qs = (ExamAttempt.objects.filter(student=user, status=ExamAttempt.Status.IN_PROGRESS)
          .select_related("exam").prefetch_related("answers", "speaking_submissions"))
    for a in qs:
        answers = [x for x in a.answers.all() if x.answer or x.selected_option_id]
        recordings = list(a.speaking_submissions.all())
        last = max([a.started_at] + [x.answered_at for x in answers] + [r.submitted_at for r in recordings])
        if a.exam.is_objective:
            saved = ngettext("%(n)d answer saved", "%(n)d answers saved", len(answers)) % {"n": len(answers)}
        elif a.exam.section == Section.SPEAKING:
            saved = ngettext("%(n)d recording saved", "%(n)d recordings saved", len(recordings)) % {"n": len(recordings)}
        else:
            words = sum(len(str(t).split()) for t in (a.drafts or {}).values())
            saved = _("draft saved · %(n)d words") % {"n": words} if words else _("no draft yet")
            if a.drafts_saved_at:
                last = max(last, a.drafts_saved_at)
        in_full = bool(a.full_mock_attempt_id)
        words = sum(len(str(t).split()) for t in (a.drafts or {}).values())
        done, total = _progress(a, answers, recordings)
        dl = attempt_services.deadline(a)
        left = (dl - timezone.now()).total_seconds() if dl else None
        items.append({
            "done": done, "total": total, "pct": round(done * 100 / total) if total else 0,
            "minutes_left": max(0, int(left // 60)) if left is not None else None,
            "expired": left is not None and left <= 0,
            "part": a.practice_label if a.practice else "",
            "exam_title": a.exam.title, "words": words,
            "attempt": a, "last": last, "saved": saved, "section": a.exam.section, "in_full": in_full,
            "title": a.exam.title + (f" · {a.practice_label}" if a.practice else ""),
            "url": reverse("exams:full_progress", args=[a.full_mock_attempt_id]) if in_full
            else reverse("exams:take", args=[a.pk]),
            **SECTION_META[a.exam.section],
        })
    return sorted(items, key=lambda i: i["last"], reverse=True)


def _progress(attempt, answers, recordings):
    """(done, total) for the progress bar of an unfinished attempt."""
    if attempt.exam.is_objective:
        return len(answers), attempt_services.attempt_questions(attempt).count()
    if attempt.exam.section == Section.SPEAKING:
        return len(recordings), attempt_services.attempt_speaking_questions(attempt).count()
    drafts = attempt.drafts or {}
    tasks = list(attempt_services.attempt_tasks(attempt).values_list("pk", flat=True))
    return sum(1 for pk in tasks if str(drafts.get(str(pk), "")).strip()), len(tasks)


def mock_library():
    mocks = dict(MockExam.objects.published().values_list("section").annotate(n=Count("id")))
    peak = max(mocks.values(), default=0) or 1
    sections = [{"key": k, "label": label, "n": mocks.get(k, 0), "pct": round(mocks.get(k, 0) * 100 / peak),
                 **SECTION_META[k]} for k, label in Section.choices]
    return {"total": sum(mocks.values()), "sections": sections}


# --------------------------------------------------------------- per user
def activity(user):
    """Streak, daily counts, 7-day bars and day/night split for one student."""
    starts = [timezone.localtime(t) for t in
              ExamAttempt.objects.filter(student=user).values_list("started_at", flat=True)]
    today = timezone.localdate()
    days = {t.date() for t in starts}

    streak = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)

    week_start = today - timedelta(days=6)
    per_day = {}
    for t in starts:
        if t.date() >= week_start:
            per_day[t.date()] = per_day.get(t.date(), 0) + 1
    peak = max(per_day.values(), default=0) or 1
    week = [{"label": (week_start + timedelta(days=i)).strftime("%a")[:2],
             "n": per_day.get(week_start + timedelta(days=i), 0),
             "pct": round(per_day.get(week_start + timedelta(days=i), 0) * 100 / peak)} for i in range(7)]

    day_n = sum(1 for t in starts if t.hour in DAY_HOURS)
    night_n = len(starts) - day_n
    total = len(starts)
    circumference = 2 * 3.14159 * 42  # donut radius 42
    return {
        "streak": streak,
        "today": per_day.get(today, 0),
        "this_week": sum(per_day.values()),
        "active_days": len(days),
        "week": week,
        "day": day_n, "night": night_n, "total": total,
        "day_pct": round(day_n * 100 / total) if total else 0,
        "night_pct": round(night_n * 100 / total) if total else 0,
        "donut_day": round(circumference * day_n / total, 1) if total else 0,
        "donut_circ": round(circumference, 1),
    }


def _completed(user):
    """Completed full tests. Part practice is shown in the history but never counts toward
    scores, levels or the learning curve."""
    return (ExamAttempt.objects.filter(student=user, status=ExamAttempt.Status.COMPLETED, practice="")
            .select_related("exam", "result").order_by("completed_at", "pk"))


def learning_curve(user, last=10):
    """Line chart (SVG points) of the last N completed scores on the 0–75 scale."""
    points = [(a, score75(a)) for a in _completed(user)]
    points = [(a, s) for a, s in points if s is not None][-last:]
    if not points:
        return None
    width, height, pad = 600, 140, 8
    n = len(points)
    coords = []
    for i, (_, s) in enumerate(points):
        x = pad + (width - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)
        y = pad + (height - 2 * pad) * (1 - s / float(MAX_SCORE))
        coords.append((round(x, 1), round(y, 1)))
    if n == 1:
        coords = [(pad, coords[0][1]), (width - pad, coords[0][1])]
    line = " ".join(f"{x},{y}" for x, y in coords)
    area = f"{coords[0][0]},{height} {line} {coords[-1][0]},{height}"
    first, latest = points[0][1], points[-1][1]
    b1_y = round(pad + (height - 2 * pad) * (1 - 38 / float(MAX_SCORE)), 1)
    return {
        "line": line, "area": area, "width": width, "height": height, "b1_y": b1_y,
        "level": multilevel_to_cefr(latest), "latest": round(latest), "count": n,
        "change": round(latest - first) if n > 1 else None,
    }


def skill_levels(user):
    """Latest level per skill with a 0–75 fill bar."""
    out = []
    completed = list(_completed(user))
    for key, label in Section.choices:
        rows = [a for a in completed if a.exam.section == key]
        latest = score75(rows[-1]) if rows else None
        out.append({"key": key, "label": label, **SECTION_META[key], "count": len(rows),
                    "score": round(latest) if latest is not None else None,
                    "level": multilevel_to_cefr(latest) if latest is not None else "",
                    "pct": round(latest * 100 / float(MAX_SCORE)) if latest is not None else 0})
    return out


def results_overview(user):
    attempts = ExamAttempt.objects.filter(student=user)
    completed = list(_completed(user))
    scores = [s for s in (score75(a) for a in completed) if s is not None]
    first = attempts.order_by("started_at").values_list("started_at", flat=True).first()
    ai = (WritingEvaluation.objects.filter(submission__student=user).exclude(provider="rule").count()
          + SpeakingEvaluation.objects.filter(submission__student=user).exclude(provider="rule").count())
    best = max(scores) if scores else None
    return {
        "total": attempts.exclude(status__in=[ExamAttempt.Status.IN_PROGRESS, ExamAttempt.Status.DISCARDED]).count(),
        "since": first,
        "best": round(best) if best is not None else None,
        "best_level": multilevel_to_cefr(best) if best is not None else "",
        "latest": round(scores[-1]) if scores else None,
        "skills": len({a.exam.section for a in completed}),
        "ai_analysed": ai,
    }


def progression(user, section="", last=12):
    """Bars for the last N scored attempts, coloured by section."""
    rows = [a for a in _completed(user) if not section or a.exam.section == section]
    bars = []
    for a in rows[-last:]:
        s = score75(a)
        if s is None:
            continue
        bars.append({"score": round(s), "pct": max(3, round(s * 100 / float(MAX_SCORE))),
                     "color": SECTION_META[a.exam.section]["color"], "date": timezone.localtime(a.completed_at),
                     "section": a.exam.get_section_display(), "url": a.get_absolute_url()})
    return bars


def attempt_parts(attempt):
    """Short description of what an attempt contained (tasks / parts)."""
    section = attempt.exam.section
    if attempt.practice:
        return attempt.practice_label
    if section == Section.WRITING:
        return ", ".join(attempt.writing_submissions.values_list("task__title", flat=True))
    if section == Section.SPEAKING:
        parts = sorted(set(attempt.speaking_submissions.values_list("question__part", flat=True)))
        from exams.models import SpeakingQuestion

        return ", ".join(SpeakingQuestion.SHORT_LABELS.get(p, f"Part {p}") for p in parts)
    if attempt.status == ExamAttempt.Status.COMPLETED:
        total = attempt.correct_count + attempt.incorrect_count + attempt.unanswered_count
        return _("%(n)d/%(total)d correct") % {"n": attempt.correct_count, "total": total} if total else ""
    return ""


def greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return _("Good morning")
    if hour < 18:
        return _("Good afternoon")
    return _("Good evening")
