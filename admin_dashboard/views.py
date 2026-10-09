"""Admin dashboard (/admin-dashboard/). Every view requires role=admin."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from ai.services import AIService
from core.mixins import admin_required
from dashboard.services import student_stats
from exams import services as exam_services
from exams.models import ExamPart, FullMock, MockExam, Question, Section, SpeakingQuestion, WritingTask
from results.models import ExamAttempt, FullMockAttempt
from speaking import services as speaking_services
from speaking.models import SpeakingStatus, SpeakingSubmission
from writing import services as writing_services
from writing.models import ProcessingStatus, WritingSubmission

from .forms import (
    AdminUserForm,
    FullMockForm,
    ExamOptionFormSet,
    ExamPartForm,
    ExamQuestionForm,
    MockExamForm,
    SpeakingQuestionForm,
    WritingTaskForm,
    validate_question_answer,
)
from .services import filter_attempts, filter_speaking, filter_writing

PORTAL = {"portal": "admin"}


def _page(request, qs, per=25):
    return Paginator(qs, per).get_page(request.GET.get("page"))


def _form_page(request, form, title, back_url, **extra):
    return render(request, "portal/form.html", {"form": form, "title": title, "back_url": back_url, **PORTAL, **extra})


# ---------------------------------------------------------------- home
@admin_required
def home(request):
    today = timezone.localdate()
    attempts = ExamAttempt.objects.all()
    completed = attempts.filter(status=ExamAttempt.Status.COMPLETED)
    by_section = {r["exam__section"]: r for r in attempts.values("exam__section").annotate(
        n=Count("id"), avg=Avg("percentage", filter=Q(status=ExamAttempt.Status.COMPLETED)))}
    stats = {
        "students": User.objects.filter(role=User.Role.STUDENT, is_guest=False).count(),
        "full_mocks": FullMock.objects.filter(is_published=True).count(),
        "full_sittings": FullMockAttempt.objects.count(),
        "exams": MockExam.objects.count(),
        "published_exams": MockExam.objects.filter(is_published=True).count(),
        "attempts": attempts.count(),
        "today": attempts.filter(started_at__date=today).count(),
        "writing": WritingSubmission.objects.count(),
        "speaking": SpeakingSubmission.objects.count(),
        "reading": by_section.get("reading", {}).get("n", 0),
        "listening": by_section.get("listening", {}).get("n", 0),
        "avg_score": completed.aggregate(a=Avg("percentage"))["a"],
        "ai_failed": (WritingSubmission.objects.filter(status=ProcessingStatus.FAILED).count()
                      + SpeakingSubmission.objects.filter(processing_status=SpeakingStatus.FAILED).count()),
    }
    section_avgs = [(label, by_section.get(key, {}).get("avg"), by_section.get(key, {}).get("n", 0))
                    for key, label in Section.choices]
    start = today - timedelta(days=13)
    daily = dict(attempts.filter(started_at__date__gte=start).annotate(d=TruncDate("started_at"))
                 .values_list("d").annotate(n=Count("id")))
    days = [(start + timedelta(days=i), daily.get(start + timedelta(days=i), 0)) for i in range(14)]
    peak = max((n for _, n in days), default=0) or 1
    chart = [{"day": d, "n": n, "pct": round(n * 100 / peak)} for d, n in days]
    recent = attempts.select_related("student", "exam", "result").order_by("-started_at")[:10]
    return render(request, "admin_dashboard/home.html", {
        "stats": stats, "section_avgs": section_avgs, "chart": chart, "recent": recent, **PORTAL})


# --------------------------------------------------------------- users
@admin_required
def users(request):
    qs = User.objects.filter(is_guest=False).annotate(
        exams_completed=Count("exam_attempts", filter=Q(exam_attempts__status=ExamAttempt.Status.COMPLETED),
                              distinct=True),
    )
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q))
    if role in User.Role.values:
        qs = qs.filter(role=role)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    return render(request, "admin_dashboard/users.html", {
        "page": _page(request, qs.order_by("-date_joined")), "q": q, "role": role, "status": status,
        "roles": User.Role.choices, **PORTAL})


@admin_required
def user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    attempts = ExamAttempt.objects.filter(student=user).select_related("exam", "result")
    return render(request, "admin_dashboard/user_detail.html", {
        "u": user,
        "stats": student_stats(user),
        "attempts": attempts[:50],
        "objective_attempts": attempts.filter(exam__section__in=["reading", "listening"])[:30],
        "writing": WritingSubmission.objects.filter(student=user).select_related("task", "attempt__exam",
                                                                                 "evaluation")[:30],
        "speaking": SpeakingSubmission.objects.filter(student=user).select_related("question", "exam",
                                                                                   "evaluation")[:30],
        "full_attempts": FullMockAttempt.objects.filter(student=user).select_related("full_mock")[:30],
        **PORTAL,
    })


@admin_required
def user_create(request):
    form = AdminUserForm(request.POST or None, request.FILES or None, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"User {user.email} created.")
        return redirect("admin_dashboard:user_detail", pk=user.pk)
    return _form_page(request, form, "Add user", reverse("admin_dashboard:users"))


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminUserForm(request.POST or None, request.FILES or None, instance=user, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User saved.")
        return redirect("admin_dashboard:user_detail", pk=user.pk)
    return _form_page(request, form, f"Edit {user.get_full_name()}", reverse("admin_dashboard:user_detail",
                                                                              args=[user.pk]))


@admin_required
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.email} {'activated' if user.is_active else 'deactivated'}.")
    return redirect(request.POST.get("next") or reverse("admin_dashboard:user_detail", args=[pk]))


# ---------------------------------------------------------------- mocks
def _section_or_404(section):
    if section not in Section.values:
        raise Http404
    return section


@admin_required
def mocks(request, section):
    _section_or_404(section)
    qs = (MockExam.objects.filter(section=section)
          .annotate(attempts_n=Count("attempts", distinct=True)).order_by("-created_at"))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(title__icontains=q)
    return render(request, "admin_dashboard/mocks.html", {
        "page": _page(request, qs), "section": section, "section_label": Section(section).label,
        "q": q, **PORTAL})


@admin_required
def mock_create(request, section):
    _section_or_404(section)
    form = MockExamForm(request.POST or None, request.FILES or None, section=section,
                        initial={"time_limit": {"reading": 60, "listening": 40, "writing": 60, "speaking": 15}[section]})
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.section = section
        exam.created_by = request.user
        exam.is_published = False
        exam.save()
        if form.cleaned_data.get("cefr_layout"):
            exam_services.create_cefr_parts(exam)
            messages.success(request, "Mock created with the official CEFR parts. Add the texts and questions, "
                                      "then publish.")
        else:
            messages.success(request, "Mock created. Now add its content, then publish.")
        return redirect("admin_dashboard:mock_manage", pk=exam.pk)
    return _form_page(request, form, f"Add {Section(section).label} mock",
                      reverse("admin_dashboard:mocks", args=[section]))


@admin_required
def mock_edit(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    form = MockExamForm(request.POST or None, request.FILES or None, instance=exam)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Mock saved.")
        return redirect("admin_dashboard:mock_manage", pk=exam.pk)
    return _form_page(request, form, f"Edit: {exam.title}", reverse("admin_dashboard:mock_manage", args=[pk]))


@admin_required
def mock_delete(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    attempts = exam.attempts.count()
    in_full = FullMock.objects.filter(Q(listening=exam) | Q(reading=exam) | Q(writing=exam) | Q(speaking=exam))
    if request.method == "POST":
        if in_full.exists():
            messages.error(request, f"This mock is part of the full mock “{in_full.first().title}”. Remove it there first.")
            return redirect("admin_dashboard:mock_manage", pk=pk)
        if attempts:
            messages.error(request, "This mock has student attempts and cannot be deleted. Unpublish it instead.")
            return redirect("admin_dashboard:mock_manage", pk=pk)
        section = exam.section
        exam.delete()
        messages.success(request, "Mock deleted.")
        return redirect("admin_dashboard:mocks", section=section)
    return render(request, "portal/confirm_delete.html", {
        "object": exam, "back_url": reverse("admin_dashboard:mock_manage", args=[pk]),
        "warning": (f"{attempts} attempt(s) exist — deletion is blocked to preserve student results."
                    if attempts else "All questions/tasks of this mock will be deleted."),
        "blocked": bool(attempts), **PORTAL})


@admin_required
@require_POST
def mock_toggle_publish(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    if not exam.is_published:
        problems = exam_services.validate_publishable(exam)
        if problems:
            for p in problems[:8]:
                messages.error(request, p)
            return redirect("admin_dashboard:mock_manage", pk=pk)
    exam.is_published = not exam.is_published
    exam.save(update_fields=["is_published", "updated_at"])
    messages.success(request, "Published." if exam.is_published else "Unpublished.")
    return redirect(request.POST.get("next") or reverse("admin_dashboard:mock_manage", args=[pk]))


@admin_required
@require_POST
def mock_duplicate(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    copy = exam_services.duplicate_exam(exam, request.user)
    messages.success(request, f"Duplicated as “{copy.title}” (unpublished).")
    return redirect("admin_dashboard:mock_manage", pk=copy.pk)


@admin_required
def mock_manage(request, pk):
    exam = get_object_or_404(MockExam, pk=pk)
    ctx = {"exam": exam, "attempts_n": exam.attempts.count(), **PORTAL}
    if exam.is_objective:
        from exams import cefr

        parts = list(exam.parts.prefetch_related("questions__options"))
        ctx["parts"] = parts
        by_code = {p.cefr_part: p for p in parts if p.cefr_part}
        labels = dict(Question.Type.choices)
        ctx["cefr_structure"] = [{**preset, "part": by_code.get(preset["code"]),
                                  "type_labels": ", ".join(labels[t].split(" (")[0] for t in preset["types"]),
                                  "n": len(by_code[preset["code"]].questions.all()) if preset["code"] in by_code else 0}
                                 for preset in cefr.structure(exam.section)]
    elif exam.section == Section.WRITING:
        ctx["tasks"] = exam.writing_tasks.all()
    else:
        ctx["speaking_questions"] = exam.speaking_questions.all()
    ctx["problems"] = exam_services.validate_publishable(exam) if not exam.is_published else []
    return render(request, "admin_dashboard/mock_manage.html", ctx)


def _manage_url(exam_id):
    return reverse("admin_dashboard:mock_manage", args=[exam_id])


@admin_required
def part_form(request, exam_pk=None, pk=None):
    part = get_object_or_404(ExamPart, pk=pk) if pk else None
    exam = part.exam if part else get_object_or_404(MockExam, pk=exam_pk)
    if not exam.is_objective:
        raise Http404
    initial = None
    if not part:
        from exams import cefr

        preset = cefr.PARTS.get(request.GET.get("preset", ""))
        order = exam_services.next_part_order(exam)
        initial = {"order": order, "title": f"Part {order}"}
        if preset:
            initial = {"order": int(preset["code"][1:]), "title": preset["title"], "cefr_part": preset["code"],
                       "instructions": preset["instructions"]}
    form = ExamPartForm(request.POST or None, request.FILES or None, instance=part, section=exam.section,
                        initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.exam = exam
        obj.save()
        messages.success(request, "Saved.")
        return redirect(_manage_url(exam.pk))
    return _form_page(request, form, f"{'Edit' if part else 'Add'} part", _manage_url(exam.pk))


@admin_required
def part_delete(request, pk):
    part = get_object_or_404(ExamPart, pk=pk)
    if request.method == "POST":
        if part.questions.filter(answers__isnull=False).exists():
            messages.error(request, "Questions in this part have student answers; it cannot be deleted.")
        else:
            part.delete()
            messages.success(request, "Deleted.")
        return redirect(_manage_url(part.exam_id))
    return render(request, "portal/confirm_delete.html", {"object": part, "back_url": _manage_url(part.exam_id),
                                                          "warning": "All questions in this part will be deleted.",
                                                          **PORTAL})


@admin_required
def question_form(request, part_pk=None, pk=None):
    question = get_object_or_404(Question, pk=pk) if pk else None
    part = question.part if question else get_object_or_404(ExamPart, pk=part_pk)
    exam = part.exam
    form = ExamQuestionForm(request.POST or None, instance=question, part=part,
                            initial=None if question else {"order": exam_services.next_question_number(exam)})
    formset = ExamOptionFormSet(request.POST or None, instance=question or Question(part=part), prefix="opt")
    if request.method == "POST":
        formset.question_type = request.POST.get("question_type")
        formset.correct_answer = request.POST.get("correct_answer", "")
        if form.is_valid() and validate_question_answer(form) and formset.is_valid():
            with transaction.atomic():
                q = form.save(commit=False)
                q.part = part
                q.save()
                formset.instance = q
                formset.save()
                if q.question_type not in Question.CHOICE_TYPES:
                    q.options.all().delete()
            messages.success(request, "Question saved.")
            if "save_add" in request.POST:
                return redirect("admin_dashboard:question_create", part_pk=part.pk)
            return redirect(_manage_url(exam.pk))
    from exams import cefr

    return render(request, "admin_dashboard/question_form.html", {
        "form": form, "formset": formset, "part": part, "exam": exam, "question": question,
        "preset": cefr.PARTS.get(part.cefr_part),
        "back_url": _manage_url(exam.pk), **PORTAL})


@admin_required
def question_delete(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if request.method == "POST":
        if question.answers.exists():
            messages.error(request, "This question has student answers and cannot be deleted.")
        else:
            question.delete()
            messages.success(request, "Question deleted.")
        return redirect(_manage_url(question.exam_id))
    return render(request, "portal/confirm_delete.html", {"object": question,
                                                          "back_url": _manage_url(question.exam_id), **PORTAL})


@admin_required
def task_form(request, exam_pk=None, pk=None):
    task = get_object_or_404(WritingTask, pk=pk) if pk else None
    exam = task.exam if task else get_object_or_404(MockExam, pk=exam_pk, section=Section.WRITING)
    initial = None
    if not task:
        n = exam.writing_tasks.count() + 1
        defaults = {
            1: ("task1_1", "Task 1.1", 50, 70, 15),
            2: ("task1_2", "Task 1.2", 120, 150, 20),
            3: ("task2", "Task 2", 180, 200, 25),
        }
        task_type, title, low, high, minutes = defaults.get(n, ("task2", f"Task {n}", 180, 200, 25))
        initial = {"order": n, "task_type": task_type, "title": title, "minimum_word_count": low,
                   "maximum_word_count": high, "time_limit": minutes}
    form = WritingTaskForm(request.POST or None, request.FILES or None, instance=task, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.exam = exam
        obj.save()
        messages.success(request, "Writing task saved.")
        return redirect(_manage_url(exam.pk))
    return _form_page(request, form, f"{'Edit' if task else 'Add'} writing task", _manage_url(exam.pk))


@admin_required
def task_delete(request, pk):
    task = get_object_or_404(WritingTask, pk=pk)
    if request.method == "POST":
        if task.submissions.exists():
            messages.error(request, "This task has submissions; unpublish it instead of deleting.")
        else:
            task.delete()
            messages.success(request, "Task deleted.")
        return redirect(_manage_url(task.exam_id))
    return render(request, "portal/confirm_delete.html", {"object": task, "back_url": _manage_url(task.exam_id),
                                                          **PORTAL})


@admin_required
def speaking_question_form(request, exam_pk=None, pk=None):
    sq = get_object_or_404(SpeakingQuestion, pk=pk) if pk else None
    exam = sq.exam if sq else get_object_or_404(MockExam, pk=exam_pk, section=Section.SPEAKING)
    initial = None
    if not sq:
        part = int(request.GET.get("part", 1)) if request.GET.get("part", "1").isdigit() else 1
        part = part if part in SpeakingQuestion.DEFAULT_TIMES else 1
        prep, speak = SpeakingQuestion.DEFAULT_TIMES.get(part, (5, 30))
        initial = {"part": part, "order": exam.speaking_questions.filter(part=part).count() + 1,
                   "preparation_time": prep, "speaking_time": speak}
    form = SpeakingQuestionForm(request.POST or None, request.FILES or None, instance=sq, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.exam = exam
        obj.save()
        messages.success(request, "Speaking question saved.")
        if "save_add" in request.POST:
            return redirect(reverse("admin_dashboard:speaking_question_create", args=[exam.pk]) + f"?part={obj.part}")
        return redirect(_manage_url(exam.pk))
    return _form_page(request, form, f"{'Edit' if sq else 'Add'} speaking question", _manage_url(exam.pk),
                      save_add=True)


@admin_required
def speaking_question_delete(request, pk):
    sq = get_object_or_404(SpeakingQuestion, pk=pk)
    if request.method == "POST":
        if sq.submissions.exists():
            messages.error(request, "This question has recordings and cannot be deleted.")
        else:
            sq.delete()
            messages.success(request, "Question deleted.")
        return redirect(_manage_url(sq.exam_id))
    return render(request, "portal/confirm_delete.html", {"object": sq, "back_url": _manage_url(sq.exam_id),
                                                          **PORTAL})


# ---------------------------------------------------------- submissions
@admin_required
def writing_submissions(request):
    qs, filters = filter_writing(request.GET)
    return render(request, "admin_dashboard/writing_list.html", {
        "page": _page(request, qs), "f": filters, "statuses": ProcessingStatus.choices,
        **PORTAL})


@admin_required
def writing_detail(request, pk):
    sub = get_object_or_404(WritingSubmission.objects.select_related("student", "task", "attempt__exam", "evaluation"),
                            pk=pk)
    return render(request, "admin_dashboard/writing_detail.html", {"sub": sub, "ev": getattr(sub, "evaluation", None),
                                                                   **PORTAL})


@admin_required
@require_POST
def writing_retry(request, pk):
    sub = get_object_or_404(WritingSubmission, pk=pk)
    writing_services.retry_evaluation(sub)
    messages.success(request, "AI evaluation re-queued.")
    return redirect("admin_dashboard:writing_detail", pk=pk)


@admin_required
def speaking_submissions(request):
    qs, filters = filter_speaking(request.GET)
    return render(request, "admin_dashboard/speaking_list.html", {
        "page": _page(request, qs), "f": filters, "statuses": SpeakingStatus.choices,
        **PORTAL})


@admin_required
def speaking_detail(request, pk):
    sub = get_object_or_404(SpeakingSubmission.objects.select_related("student", "question", "exam", "evaluation"),
                            pk=pk)
    return render(request, "admin_dashboard/speaking_detail.html", {"sub": sub, "ev": getattr(sub, "evaluation", None),
                                                                    **PORTAL})


@admin_required
@require_POST
def speaking_retry(request, pk):
    sub = get_object_or_404(SpeakingSubmission, pk=pk)
    speaking_services.retry_processing(sub)
    messages.success(request, "Recording re-queued for transcription and evaluation.")
    return redirect("admin_dashboard:speaking_detail", pk=pk)


@admin_required
def results(request):
    qs, filters = filter_attempts(request.GET)
    return render(request, "admin_dashboard/results.html", {
        "page": _page(request, qs), "f": filters, "sections": Section.choices,
        "statuses": ExamAttempt.Status.choices, **PORTAL})


# -------------------------------------------------------------- settings
@admin_required
def settings_page(request):
    if request.method == "POST" and request.POST.get("action") == "process_queue":
        from ai.tasks import _get_executor, _run

        w = list(WritingSubmission.objects.filter(status=ProcessingStatus.PENDING).values_list("pk", flat=True)[:50])
        s = list(SpeakingSubmission.objects.filter(processing_status=SpeakingStatus.PENDING)
                 .values_list("pk", flat=True)[:50])
        for pk in w:
            _get_executor().submit(_run, writing_services.evaluate_submission, pk)
        for pk in s:
            _get_executor().submit(_run, speaking_services.process_submission, pk)
        messages.success(request, f"Started processing {len(w)} writing and {len(s)} speaking item(s).")
        return redirect("admin_dashboard:settings")
    return render(request, "admin_dashboard/settings.html", {
        "ai": AIService.status(), "limits": settings.UPLOAD_LIMITS_MB, "use_s3": settings.USE_S3,
        "debug": settings.DEBUG, "grace": settings.EXAM_SUBMIT_GRACE_SECONDS,
        "pending": {
            "writing": WritingSubmission.objects.filter(status=ProcessingStatus.PENDING).count(),
            "speaking": SpeakingSubmission.objects.filter(processing_status=SpeakingStatus.PENDING).count(),
            "writing_failed": WritingSubmission.objects.filter(status=ProcessingStatus.FAILED).count(),
            "speaking_failed": SpeakingSubmission.objects.filter(processing_status=SpeakingStatus.FAILED).count(),
        },
        **PORTAL})


# ------------------------------------------------------------ full mocks
@admin_required
def full_mocks(request):
    qs = (FullMock.objects.select_related("listening", "reading", "writing", "speaking")
          .annotate(sittings=Count("attempts")).order_by("-created_at"))
    return render(request, "admin_dashboard/full_mocks.html", {"page": _page(request, qs), **PORTAL})


@admin_required
def full_mock_form(request, pk=None):
    fm = get_object_or_404(FullMock, pk=pk) if pk else None
    form = FullMockForm(request.POST or None, instance=fm)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not fm:
            obj.created_by = request.user
        if obj.is_published and obj.publish_problems():
            obj.is_published = False
            messages.warning(request, "Unpublished because a linked section mock is not published.")
        obj.save()
        messages.success(request, "Full mock saved.")
        return redirect("admin_dashboard:full_mock_detail", pk=obj.pk)
    return _form_page(request, form, "Edit full mock" if fm else "Add full mock",
                      reverse("admin_dashboard:full_mocks"))


@admin_required
def full_mock_detail(request, pk):
    fm = get_object_or_404(FullMock.objects.select_related("listening", "reading", "writing", "speaking"), pk=pk)
    sittings = fm.attempts.select_related("student").order_by("-started_at")
    return render(request, "admin_dashboard/full_mock_detail.html", {
        "fm": fm, "page": _page(request, sittings), "problems": fm.publish_problems(), **PORTAL})


@admin_required
@require_POST
def full_mock_publish(request, pk):
    fm = get_object_or_404(FullMock, pk=pk)
    if not fm.is_published:
        problems = fm.publish_problems()
        if problems:
            for p in problems:
                messages.error(request, p)
            return redirect("admin_dashboard:full_mock_detail", pk=pk)
    fm.is_published = not fm.is_published
    fm.save(update_fields=["is_published", "updated_at"])
    messages.success(request, "Published." if fm.is_published else "Unpublished.")
    return redirect(request.POST.get("next") or reverse("admin_dashboard:full_mock_detail", args=[pk]))


@admin_required
def full_mock_delete(request, pk):
    fm = get_object_or_404(FullMock, pk=pk)
    sittings = fm.attempts.count()
    if request.method == "POST":
        if sittings:
            messages.error(request, "This full mock has student sittings; unpublish it instead.")
            return redirect("admin_dashboard:full_mock_detail", pk=pk)
        fm.delete()
        messages.success(request, "Full mock deleted.")
        return redirect("admin_dashboard:full_mocks")
    return render(request, "portal/confirm_delete.html", {
        "object": fm, "back_url": reverse("admin_dashboard:full_mock_detail", args=[pk]), "blocked": bool(sittings),
        "warning": (f"{sittings} sitting(s) exist — deletion is blocked to keep student results."
                    if sittings else "The section mocks themselves are not deleted."), **PORTAL})


# ------------------------------------------------------------ quick entry
def _quick_render(request, template, ctx):
    return render(request, template, {**ctx, **PORTAL})


@admin_required
def quick_part(request, pk):
    """Passage + every question of one Reading/Listening part on a single page, as plain text."""
    from exams import cefr

    from . import quick

    part = get_object_or_404(ExamPart.objects.select_related("exam"), pk=pk)
    exam = part.exam
    locked = quick.part_locked(part)
    passage = request.POST.get("passage", part.passage) if request.method == "POST" else part.passage
    text = request.POST.get("questions", "") if request.method == "POST" else quick.serialize_part(part)
    items, errors = ([], [])
    missing = []
    if request.method == "POST":
        items, errors = quick.parse_part(text, part)
        passage = quick.normalize_gaps(passage, {it.number for it in items if it.qtype == "gap_filling"})
        missing = quick.missing_gaps(passage, items) if passage.strip() else []
        if request.POST.get("action") == "save" and not errors:
            if locked:
                messages.error(request, "Students have already answered this part. Duplicate the mock to change it.")
            else:
                from django.core.exceptions import ValidationError

                part.passage = passage
                for name in ("audio", "image"):
                    if request.FILES.get(name):
                        setattr(part, name, request.FILES[name])
                try:
                    part.full_clean(exclude=["exam"])
                except ValidationError as e:
                    errors = [f"{k.title()}: {' '.join(v)}" for k, v in e.message_dict.items()]
                else:
                    part.save()
                    n = quick.apply_part(part, items)
                    messages.success(request, f"Saved {part.title}: {n} question{'s' if n != 1 else ''}.")
                    return redirect(f"{_manage_url(exam.pk)}?quick_saved={request.path}")
    preset = cefr.PARTS.get(part.cefr_part or "")
    return _quick_render(request, "admin_dashboard/quick_part.html", {
        "part": part, "exam": exam, "preset": preset, "passage": passage, "text": text, "items": items,
        "errors": errors, "locked": locked, "previewed": request.method == "POST", "missing": missing,
        "type_labels": {"gap_filling": "Gap filling", "multiple_choice": "Multiple choice",
                        "true_false_not_given": "True / False / NG", "matching": "Matching",
                        "headings": "Headings", "map_labelling": "Map"},
    })


@admin_required
def quick_speaking(request, exam_pk):
    from . import quick

    exam = get_object_or_404(MockExam, pk=exam_pk, section=Section.SPEAKING)
    locked = quick.speaking_locked(exam)
    text = request.POST.get("text", "") if request.method == "POST" else quick.serialize_speaking(exam)
    items, errors, counts = quick.parse_speaking(text) if request.method == "POST" else ([], [], {})
    if request.method == "POST" and request.POST.get("action") == "save" and not errors:
        if locked:
            messages.error(request, "Students have already recorded answers. Duplicate the mock to change it.")
        else:
            image = request.FILES.get("image")
            if image:
                from core.validators import validate_image

                try:
                    validate_image(image)
                except Exception as e:  # noqa: BLE001 - show the validator's message
                    errors = [f"Picture: {'; '.join(getattr(e, 'messages', [str(e)]))}"]
            if not errors:
                n = quick.apply_speaking(exam, items, image=image)
                messages.success(request, f"Saved {n} speaking question{'s' if n != 1 else ''}.")
                return redirect(f"{_manage_url(exam.pk)}?quick_saved={request.path}")
    current_image = exam.speaking_questions.filter(part=2).exclude(image="").first()
    return _quick_render(request, "admin_dashboard/quick_speaking.html", {
        "exam": exam, "text": text, "items": items, "errors": errors, "counts": counts, "locked": locked,
        "previewed": request.method == "POST", "current_image": current_image,
        "part_labels": {1: "Part 1.1", 2: "Part 1.2", 3: "Part 2", 4: "Part 3"},
    })


@admin_required
def quick_writing(request, exam_pk):
    from . import quick

    exam = get_object_or_404(MockExam, pk=exam_pk, section=Section.WRITING)
    locked = quick.writing_locked(exam)
    text = request.POST.get("text", "") if request.method == "POST" else quick.serialize_writing(exam)
    items, errors, situation = quick.parse_writing(text) if request.method == "POST" else ([], [], "")
    if request.method == "POST" and request.POST.get("action") == "save" and not errors:
        if locked:
            messages.error(request, "Students have already submitted essays. Duplicate the mock to change it.")
        else:
            n = quick.apply_writing(exam, items)
            if situation and not exam.summary:
                exam.summary = situation[:80]
                exam.save(update_fields=["summary"])
            messages.success(request, f"Saved {n} writing task{'s' if n != 1 else ''}.")
            return redirect(f"{_manage_url(exam.pk)}?quick_saved={request.path}")
    return _quick_render(request, "admin_dashboard/quick_writing.html", {
        "exam": exam, "text": text, "items": items, "errors": errors, "locked": locked,
        "previewed": request.method == "POST",
    })
