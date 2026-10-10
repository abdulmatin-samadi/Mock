from django.db.models import Count
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _l

from exams.models import MockExam, Section


HOME_SECTIONS = {
    "listening": {"icon": "headphones", "color": "#3b82f6", "time": _l("~35 min"),
                  "blurb": _l("Short conversations, notes, speakers, a map and a lecture — 6 parts.")},
    "reading": {"icon": "book", "color": "#f59e0b", "time": _l("60 min"),
                "blurb": _l("Gap filling, matching, headings, True/False/No Information — 5 parts.")},
    "writing": {"icon": "pen", "color": "#8b5cf6", "time": _l("60 min"),
                "blurb": _l("Informal letter, formal letter and an essay, scored by AI.")},
    "speaking": {"icon": "mic", "color": "#10b981", "time": _l("~15 min"),
                 "blurb": _l("8 questions recorded in your browser, transcribed and scored by AI.")},
}


def home(request):
    from dashboard.insights import platform_stats
    from exams.models import FullMock

    exams = MockExam.objects.published()
    counts = dict(exams.values_list("section").annotate(n=Count("id")))
    labels = dict(Section.choices)
    return render(request, "core/home.html", {
        "sections": [{"key": key, "label": labels[key], "count": counts.get(key, 0), **meta}
                     for key, meta in HOME_SECTIONS.items()],
        "mock_total": sum(counts.values()),
        "full_total": FullMock.objects.filter(is_published=True).count(),
        "stats": platform_stats(),
    })


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def csrf_failure(request, reason=""):
    """Friendly page when a form's security token is stale (usually: signed in/out in another tab)."""
    from django.utils.http import url_has_allowed_host_and_scheme

    referer = request.META.get("HTTP_REFERER", "")
    back = referer if url_has_allowed_host_and_scheme(referer, {request.get_host()}) else "/"
    return render(request, "errors/csrf.html", {"back": back}, status=403)
