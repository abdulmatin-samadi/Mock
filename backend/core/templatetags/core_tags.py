from django.utils.safestring import mark_safe
from django import template
from django.utils.http import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Keep current GET params but replace some (for pagination with filters)."""
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ""):
            params.pop(k, None)
        else:
            params[k] = v
    return "?" + urlencode(params, doseq=True) if params else "?"


@register.filter
def duration(seconds):
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return "—"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def score_class(percentage):
    try:
        p = float(percentage)
    except (TypeError, ValueError):
        return "neutral"
    if p >= 75:
        return "good"
    if p >= 50:
        return "ok"
    return "low"


@register.inclusion_tag("partials/status_badge.html")
def status_badge(status, label=None):
    return {"status": status, "label": label or str(status).replace("_", " ").title()}


@register.filter
def filesize(num):
    try:
        num = float(num)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


@register.simple_tag
def vstatic(path):
    """Static URL with a ?v=<modified time> suffix so browsers fetch new CSS/JS after every change."""
    import os

    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    url = static(path)
    found = finders.find(path)
    if found:
        url += f"?v={int(os.path.getmtime(found))}"
    return url


@register.simple_tag
def js_i18n():
    """<script> with the JavaScript texts in the current language (read by DreamZone.t())."""
    import json

    from django.utils.html import format_html
    from django.utils.translation import gettext

    from core.js_strings import JS_STRINGS

    data = json.dumps({s: gettext(s) for s in JS_STRINGS}, ensure_ascii=False)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return format_html('<script id="dz-i18n" type="application/json">{}</script>', mark_safe(data))
