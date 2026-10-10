
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.utils.translation import gettext

from core.media import serve_private_file
from results import services as result_services
from results.models import ExamAttempt, FullMockAttempt

from .cards import mock_cards
from .room import build_part, mock_number
from .models import ExamPart, FullMock, MockExam, Question, Section
from .services import can_access_exam_media

SECTION_INFO = {
    "reading": {"icon": "📖", "color": "#f59e0b",
                "blurb": "Gap filling, matching, headings, True/False/No Information and multiple choice.",
                "format": ["Gap filling", "Matching", "True / False / No Information", "Multiple choice"]},
    "listening": {"icon": "🎧", "color": "#3b82f6",
                  "blurb": "Short dialogues, a monologue and a longer conversation with timed questions.",
                  "format": ["Part 1 · short dialogues", "Part 2 · note completion", "Part 3 · conversation"]},
    "writing": {"icon": "✍️", "color": "#8b5cf6",
                "blurb": "Three tasks in 60 minutes, evaluated by AI on the Multilevel 0–75 scale.",
                "format": ["Task 1.1 · informal letter · 50–70 words", "Task 1.2 · formal letter · 120–150 words",
                           "Task 2 · essay · 180–200 words"]},
    "speaking": {"icon": "🎙️", "color": "#10b981",
                 "blurb": "8 questions recorded in the browser, transcribed and evaluated by AI.",
                 "format": ["Part 1.1 · 3 personal questions · 30 s", "Part 1.2 · picture comparison · 45 s + 30 s",
                            "Part 2 · long turn · 2 min", "Part 3 · argument · 2 min"]},
}


def hub(request):
    from dashboard import insights

    full_mocks = FullMock.objects.filter(is_published=True)
    return render(request, "exams/hub.html", {
        "sections": insights.section_cards(),
        "continue_items": insights.continue_items(request.user) if request.user.is_authenticated else [],
        "full_count": full_mocks.count(),
    })


def section_list(request, section):
    if section not in Section.values:
        raise Http404
    # Numbered oldest-first, like printed mock books: Mock 01, Mock 02, …
    qs = MockExam.objects.published().filter(section=section).order_by("created_at", "pk")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    offset = page.start_index() - 1 if page.paginator.count else 0
    return render(request, "exams/section_list.html", {
        "section": section, "section_label": Section(section).label, "info": SECTION_INFO[section],
        "page": page, "cards": mock_cards(page, request.user, offset),
    })


def detail(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    if not exam.is_published and not (request.user.is_authenticated and request.user.is_admin):
        raise Http404
    attempts = []
    in_progress = None
    if request.user.is_authenticated:
        attempts = list(ExamAttempt.objects.filter(student=request.user, exam=exam)
                        .exclude(status=ExamAttempt.Status.DISCARDED).select_related("result"))
        in_progress = next((a for a in attempts if a.status == ExamAttempt.Status.IN_PROGRESS
                            and not a.practice and not a.full_mock_attempt_id), None)
    options = result_services.practice_options(exam)
    guest_used = (request.user.is_authenticated and request.user.is_guest and not in_progress
                  and ExamAttempt.objects.filter(student=request.user).exists())
    return render(request, "exams/detail.html", {
        "guest_used": guest_used,
        "practice_options": options,
        "practice_minutes": round(sum(o["minutes"] or 0 for o in options) / len(options)) if options else None,
        "exam": exam, "attempts": attempts, "in_progress": in_progress, "info": SECTION_INFO[exam.section],
        "question_count": exam.question_count(),
        "parts": exam.parts.annotate(n=Count("questions")) if exam.is_objective else [],
    })


def _need_account(request, back_url, text):
    messages.info(request, text)
    return redirect(f"{reverse('accounts:register')}?next={back_url}")


@require_POST
def start(request, pk):
    from accounts import guest

    exam = get_object_or_404(MockExam, pk=pk, is_published=True)
    practice = request.POST.get("practice", "")
    user = request.user
    if not user.is_authenticated:
        user = guest.start_guest(request)
        if user is None:
            return _need_account(request, exam.get_absolute_url(),
                                 gettext("Create a free account to take this mock."))
    try:
        attempt, _ = result_services.start_attempt(user, exam, practice=practice)
    except guest.GuestLimitReached:
        return _need_account(request, exam.get_absolute_url(),
                             gettext("You've used your free mock. Create a free account to continue — your result is kept."))
    except PermissionDenied:
        messages.error(request, gettext("Only student accounts can take mock exams."))
        return redirect(exam.get_absolute_url())
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect(exam.get_absolute_url())
    return redirect("exams:take", pk=attempt.pk)


def practice(request, pk):
    """Part Practice: choose one part / task to practise on its own."""
    exam = get_object_or_404(MockExam, pk=pk)
    if not exam.is_published and not (request.user.is_authenticated and request.user.is_admin):
        raise Http404
    resume = {}
    if request.user.is_authenticated:
        for a in ExamAttempt.objects.filter(student=request.user, exam=exam, status=ExamAttempt.Status.IN_PROGRESS,
                                            full_mock_attempt__isnull=True).exclude(practice=""):
            resume[a.practice] = a
    options = result_services.practice_options(exam)
    for o in options:
        o["resume"] = resume.get(o["key"])
    return render(request, "exams/practice.html", {"exam": exam, "options": options,
                                                   "info": SECTION_INFO[exam.section]})


@login_required
def take(request, pk):
    """Exam room for an attempt. Server-rendered content never includes correct answers."""
    attempt = get_object_or_404(ExamAttempt.objects.select_related("exam"), pk=pk, student=request.user)
    exam = attempt.exam
    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        return redirect(attempt.get_absolute_url())
    if exam.is_objective and result_services.past_grace(attempt):
        result_services.grade_objective(attempt, late=True)
        messages.warning(request, gettext("Time ran out. Your saved answers were submitted automatically."))
        return redirect(attempt.get_absolute_url())

    deadline = result_services.deadline(attempt)
    config = {
        "attemptId": attempt.pk,
        "section": exam.section,
        "deadline": deadline.isoformat() if deadline else None,
        "serverNow": timezone.now().isoformat(),
        "submitUrl": reverse("attempt-submit", args=[attempt.pk]),
        "answersUrl": reverse("attempt-answers", args=[attempt.pk]),
        "attemptUrl": reverse("attempt-detail", args=[attempt.pk]),
        "resultUrl": (reverse("exams:full_progress", args=[attempt.full_mock_attempt_id])
                      if attempt.full_mock_attempt_id else attempt.get_absolute_url()),
    }
    ctx = {"attempt": attempt, "exam": exam, "deadline": deadline, "full": attempt.full_mock_attempt,
           "mock_number": mock_number(exam), "info": SECTION_INFO[exam.section],
           "exit_url": (reverse("exams:full_progress", args=[attempt.full_mock_attempt_id])
                        if attempt.full_mock_attempt_id else reverse("exams:section", args=[exam.section]))}

    if exam.is_objective:
        parts = ExamPart.objects.filter(exam=exam)
        if attempt.practice:
            parts = parts.filter(pk=attempt.practice.partition(":")[2])
        parts = list(parts.prefetch_related("questions__options"))
        saved = {a.question_id: (a.selected_option_id or a.answer) for a in attempt.answers.all()}
        config["saved"] = {str(k): v for k, v in saved.items()}
        audio = {}
        for p in parts:
            if p.audio:
                audio[str(p.pk)] = reverse("exams:part_audio", args=[p.pk])
            elif exam.audio:
                audio[str(p.pk)] = reverse("exams:audio", args=[exam.pk])
        config["audio"] = audio
        # real exam: every part has its own recording → it plays at most twice, then the next part opens
        config["examMode"] = (exam.section == Section.LISTENING and not attempt.practice
                              and bool(audio) and all(p.audio for p in parts))
        ctx.update(parts=parts, room_parts=[build_part(p) for p in parts],
                   total_questions=result_services.attempt_questions(attempt).count())
        template = "exams/take_objective.html"
    elif exam.section == Section.WRITING:
        tasks = list(result_services.attempt_tasks(attempt))
        config["tasks"] = [{"id": t.pk, "min": t.minimum_word_count, "max": t.maximum_word_count} for t in tasks]
        config["drafts"] = attempt.drafts or {}
        config["draftsUrl"] = reverse("attempt-drafts", args=[attempt.pk])
        ctx.update(tasks=tasks)
        template = "exams/take_writing.html"
    else:
        questions = list(result_services.attempt_speaking_questions(attempt))
        done = set(attempt.speaking_submissions.values_list("question_id", flat=True))
        config.update(
            uploadUrl=reverse("speaking-submission-list"),
            questions=[{"id": q.pk, "part": q.part, "partLabel": q.get_part_display(), "text": q.question,
                        "cue": [] if q.arguments else q.cue_points, "arguments": q.arguments,
                        "image": q.image.url if q.image else None,
                        "prep": q.preparation_time, "speak": q.speaking_time,
                        "done": q.pk in done} for q in questions],
        )
        ctx.update(questions=questions)
        template = "exams/take_speaking.html"
    ctx["config"] = config
    return render(request, template, ctx)


@login_required
@require_POST
def discard(request, pk):
    """Stop an unfinished attempt. Nothing is deleted — it is marked "Discarded"."""
    attempt = get_object_or_404(ExamAttempt, pk=pk, student=request.user)
    if attempt.full_mock_attempt_id:
        messages.error(request, gettext("Sections of a full mock cannot be discarded separately."))
    elif attempt.status == ExamAttempt.Status.IN_PROGRESS:
        ExamAttempt.objects.filter(pk=attempt.pk, status=ExamAttempt.Status.IN_PROGRESS).update(
            status=ExamAttempt.Status.DISCARDED)
        messages.success(request, gettext("“%(title)s” was discarded.") % {"title": attempt.exam.title})
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "dashboard:home")


@login_required
def exam_audio(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    if not can_access_exam_media(request.user, exam):
        raise PermissionDenied
    return serve_private_file(request, exam.audio)


@login_required
def part_audio(request, pk):
    part = get_object_or_404(ExamPart.objects.select_related("exam"), pk=pk)
    if not can_access_exam_media(request.user, part.exam):
        raise PermissionDenied
    return serve_private_file(request, part.audio)


# ------------------------------------------------------------- full mocks
def full_list(request):
    qs = FullMock.objects.filter(is_published=True).select_related("listening", "reading", "writing", "speaking")
    attempts = {}
    if request.user.is_authenticated:
        for a in FullMockAttempt.objects.filter(student=request.user).order_by("-started_at"):
            attempts.setdefault(a.full_mock_id, a)
    return render(request, "exams/full_list.html", {
        "page": Paginator(qs, 12).get_page(request.GET.get("page")), "attempts": attempts})


def full_detail(request, pk):
    fm = get_object_or_404(FullMock.objects.select_related("listening", "reading", "writing", "speaking"), pk=pk)
    if not fm.is_published and not (request.user.is_authenticated and request.user.is_admin):
        raise Http404
    attempts = []
    if request.user.is_authenticated:
        attempts = list(FullMockAttempt.objects.filter(student=request.user, full_mock=fm))
    in_progress = next((a for a in attempts if a.status == FullMockAttempt.Status.IN_PROGRESS), None)
    return render(request, "exams/full_detail.html", {"fm": fm, "attempts": attempts, "in_progress": in_progress,
                                                      "sections": [(s, e, SECTION_INFO[s]) for s, e in fm.sections()]})


@require_POST
def full_start(request, pk):
    from accounts.guest import GuestLimitReached

    fm = get_object_or_404(FullMock, pk=pk, is_published=True)
    if not request.user.is_authenticated:
        return _need_account(request, fm.get_absolute_url(), gettext("Create a free account to take a full mock."))
    try:
        full, _ = result_services.start_full_mock(request.user, fm)
    except GuestLimitReached:
        return _need_account(request, fm.get_absolute_url(), gettext("Create a free account to take a full mock."))
    except PermissionDenied:
        messages.error(request, gettext("Only student accounts can take full mocks."))
        return redirect(fm.get_absolute_url())
    return redirect("exams:full_progress", pk=full.pk)


@login_required
def full_progress(request, pk):
    """Between-sections page: shows the 4 steps and starts the next one."""
    full = get_object_or_404(FullMockAttempt.objects.select_related("full_mock"), pk=pk, student=request.user)
    full = result_services.refresh_full_attempt(full.pk)
    nxt = result_services.next_section(full)
    if nxt is None:
        return redirect(full.get_absolute_url())
    if request.method == "POST":
        attempt = result_services.start_next_section(full)
        return redirect("exams:take", pk=attempt.pk)
    steps = [{"section": s, "exam": e, "attempt": a, "info": SECTION_INFO[s], "number": i + 1,
              "current": nxt[0] == s} for i, (s, e, a) in enumerate(result_services.full_progress(full))]
    done = sum(1 for st in steps if st["attempt"] and st["attempt"].status != ExamAttempt.Status.IN_PROGRESS)
    return render(request, "exams/full_progress.html", {"full": full, "steps": steps, "next": nxt, "done": done})
