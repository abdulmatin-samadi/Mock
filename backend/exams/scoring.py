"""Multilevel (CEFR) score conversion.

Each skill is reported on the Multilevel 0–75 scale; CEFR thresholds follow the
national certificate: B1 38–50, B2 51–64, C1 65–75 (below 38: no level certified).
Objective sections are converted from the server-computed percentage.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
MAX_SCORE = Decimal(75)


def round_score(value):
    """Round a 0–75 score to a whole number (half up)."""
    return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def percentage_to_multilevel(percentage):
    """Multilevel (Uzbekistan national certificate) uses a 0–75 scale per skill."""
    return int((Decimal(percentage) * 75 / 100).to_integral_value(rounding=ROUND_HALF_UP))


def multilevel_to_cefr(score75):
    """Official thresholds: B1 38–50, B2 51–64, C1 65–75. Below 38 no CEFR level is certified."""
    if score75 is None:
        return ""
    s = float(score75)
    if s >= 65:
        return "C1"
    if s >= 51:
        return "B2"
    if s >= 38:
        return "B1"
    return "Below B1"


# ------------------------------------------------------------ answer checks
_ARTICLES = re.compile(r"^(the|a|an)\s+", re.I)


def normalize_text(value):
    value = (value or "").strip().lower()
    value = value.replace("’", "'").replace("‘", "'")
    value = re.sub(r"[\"“”]", "", value)
    value = re.sub(r"[.,;:!?]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def text_matches(given, accepted_pipe_list):
    """Case/space/punctuation-insensitive; leading articles are optional."""
    g = normalize_text(given)
    if not g:
        return False
    for accepted in (accepted_pipe_list or "").split("|"):
        a = normalize_text(accepted)
        if not a:
            continue
        if g == a or _ARTICLES.sub("", g) == _ARTICLES.sub("", a):
            return True
        # numbers: "1,000" == "1000"
        if g.replace(",", "") == a.replace(",", "") and re.fullmatch(r"[\d,\.]+", a):
            return True
    return False


def check_answer(question, answer_text, selected_option_id=None):
    """Return True if the student's answer is correct. Pure server-side logic."""
    from .models import Question

    t = question.question_type
    if t == Question.Type.MULTIPLE_CHOICE:
        if not selected_option_id:
            return False
        return any(o.pk == selected_option_id and o.is_correct for o in question.options.all())
    if t in Question.FIXED_CHOICES:
        given = Question.canonical_choice(normalize_text(answer_text))
        return given == Question.canonical_choice(normalize_text(question.correct_answer)) != ""
    if t in Question.LABEL_TYPES:
        return normalize_text(answer_text).upper() == normalize_text(question.correct_answer).upper() != ""
    return text_matches(answer_text, question.correct_answer)
