"""View-model for the Reading/Listening exam room.

Turns each part into: a left pane (passage with inline gaps, map image, matching
pool) and a right pane of question groups ("Questions 21–24: Multiple choice").
Correct answers are never included.
"""
import re

from .models import MockExam, Question

GAP_RE = re.compile(r"\((\d+)\)\s*_{2,}")
TEXT_TYPES = Question.TEXT_TYPES
KIND_TITLES = {
    "mcq": "Multiple choice", "choice": "True / False / No Information", "text": "Gap filling",
    "matching": "Matching", "map": "Label the map",
}


def _kind(q):
    if q.question_type == Question.Type.MULTIPLE_CHOICE:
        return "mcq"
    if q.question_type in Question.FIXED_CHOICES:
        return "choice"
    if q.question_type in (Question.Type.MATCHING, Question.Type.HEADINGS):
        return "matching"
    if q.question_type == Question.Type.MAP_LABELLING:
        return "map"
    return "text"


def _segments(passage, questions):
    """Split a passage at "(N) ______" markers whose N is a gap question of this part."""
    by_number = {q.order: q for q in questions if q.question_type in TEXT_TYPES}
    pieces = GAP_RE.split(passage or "")
    if len(pieces) == 1 or not any(int(n) in by_number for n in pieces[1::2]):
        return None, set()
    segments, used = [], set()
    for i, piece in enumerate(pieces):
        if i % 2 == 0:
            if piece:
                segments.append({"text": piece})
            continue
        q = by_number.get(int(piece))
        if q is None:
            segments.append({"text": f"({piece}) ______"})
        else:
            segments.append({"gap": q})
            used.add(q.pk)
    return segments, used


def build_part(part):
    questions = list(part.questions.all())
    segments, inline_ids = _segments(part.passage, questions)
    remaining = [q for q in questions if q.pk not in inline_ids]

    groups = []
    for q in remaining:
        kind = _kind(q)
        if groups and groups[-1]["kind"] == kind:
            groups[-1]["questions"].append(q)
        else:
            groups.append({"kind": kind, "questions": [q]})
    pool = None
    for g in groups:
        first, last = g["questions"][0].order, g["questions"][-1].order
        numbers = f"{first}–{last}" if first != last else f"{first}"
        g["title"] = f"Question{'s' if first != last else ''} {numbers}: {KIND_TITLES[g['kind']]}"
        if g["kind"] in ("matching", "map"):
            g["letters"] = [o.label for o in g["questions"][0].options.all()]
        if g["kind"] == "matching" and pool is None:
            headings = all(q.question_type == Question.Type.HEADINGS for q in g["questions"])
            pool = {"options": list(g["questions"][0].options.all()),
                    "title": "List of headings" if headings else "Statements"}

    title = _passage_title(part.passage)
    if segments:
        segments, title = segment_title(segments)
    numbers = [q.order for q in questions]
    has_left = bool(part.passage or part.image or pool)
    return {
        "part": part,
        "range": f"{min(numbers)}–{max(numbers)}" if numbers else "",
        "segments": segments,
        "passage_title": title,
        "passage_body": _passage_body(part.passage) if not segments else None,
        "groups": groups,
        "pool": pool,
        "has_left": has_left,
        # All questions answered inside the passage -> show it full width.
        "full_width": bool(segments) and not groups,
        "question_count": len(questions),
    }


def _passage_title(passage):
    first = (passage or "").strip().split("\n", 1)[0].strip()
    return first if first and first.isupper() and len(first) < 80 else ""


def _passage_body(passage):
    text = (passage or "").strip()
    if _passage_title(text):
        text = text.split("\n", 1)[1].strip() if "\n" in text else ""
    return text


def segment_title(segments):
    """Pull an UPPERCASE first line out of the first text segment as the passage title."""
    if not segments or "text" not in segments[0]:
        return segments, ""
    title = _passage_title(segments[0]["text"])
    if title:
        rest = segments[0]["text"].strip().split("\n", 1)
        segments = [{"text": rest[1].lstrip("\n") if len(rest) > 1 else ""}] + segments[1:]
    return segments, title


def mock_number(exam):
    """Position of this mock in its section list (Mock 01, 02 …), oldest first."""
    ids = list(MockExam.objects.published().filter(section=exam.section).order_by("created_at", "pk")
               .values_list("pk", flat=True))
    return ids.index(exam.pk) + 1 if exam.pk in ids else None
