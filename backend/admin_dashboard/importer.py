"""Import a whole Reading / Listening mock pasted as one text (e.g. copied from a PDF or Word file).

The text is split at its "PART 2", "Part 3" … headings. In every part, instruction sentences
("Read the text…", "Mark your answers…") are dropped, long paragraphs and sentences with gaps become
the reading text, and the rest (numbered questions, lettered options) goes through the Quick entry
parser of that CEFR part. Gaps in the text get their questions automatically, numbering that restarts
in a part is shifted to continue the mock, and an optional answer key fills in the answers.
"""
import re
from dataclasses import dataclass, field

from django.db import transaction

from exams import cefr
from exams.models import ExamPart, MockExam, Question
from exams.services import create_cefr_parts

from . import quick

PART_HEAD_RE = re.compile(r"\bpart\s*([1-6])\b(?![.\d])", re.I)
INSTRUCTION_RE = re.compile(
    r"^\s*(read the|read these|for questions|mark your answers|choose the correct|choose the answer|"
    r"choose one|decide (if|which|whether)|each statement|there are (two|three|four|more)|write no more|"
    r"write only|complete the|you will hear|you must use|you cannot use|match each|label the|look at the|"
    r"questions?\s+\d+\s*[-–]\s*\d+|use the letters|you do not need)", re.I)
SENTENCE_BEFORE_QUESTION = re.compile(r"(?<=[.?!])\s+(?=\d{1,3}\.\s+[A-Z“\"‘'])")
GAP_IN_TEXT_RE = re.compile(r"\(?\d{1,3}\)?\s*[.)]?\s*(?:_{2,}|…{2,}|\.{4,})")
ROMAN_PARAGRAPH_RE = re.compile(r"^\s*(I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+(?=\S)")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
LONG_LINE_WORDS = 30
MISSING_ANSWER_HINTS = ("write the answer", "mark exactly one correct option", "write one of the OPTIONS letters",
                        "add the answer (TRUE")


@dataclass
class PartDraft:
    number: int
    code: str
    title: str
    passage: str = ""
    questions_text: str = ""
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)    # stop this part from being saved
    warnings: list = field(default_factory=list)  # saved anyway (e.g. missing answers)
    shifted: int = 0

    @property
    def gap_numbers(self):
        return {it.number for it in self.items if it.qtype == Question.Type.GAP_FILLING}


def split_parts(text, section):
    """{part number: raw text}. Headings must come in order (1, 2, 3…), so "part 3 of the book" in a
    passage is not mistaken for one. Text before the first heading belongs to Part 1."""
    limit = len(cefr.structure(section))
    marks, expected = [], 1
    for m in PART_HEAD_RE.finditer(text or ""):
        num = int(m.group(1))
        if num == expected or (not marks and num == 1):
            marks.append((num, m.start(), m.end()))
            expected = num + 1
        if expected > limit:
            break
    if not marks:
        return {1: text or ""}
    chunks = {}
    first_num, first_start, _ = marks[0]
    lead = (text or "")[:first_start]
    for i, (num, start, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        chunks[num] = text[end:stop]
    if lead.strip():
        if first_num == 1:
            chunks[1] = lead + "\n" + chunks[1]
        else:
            chunks[1] = lead
    return chunks


def _is_question_start(line):
    s = line.strip()
    if quick.Q_RE.match(s):
        body = quick.Q_RE.match(s).group(2)
        return not re.fullmatch(r"[_….\s]*", body)  # "3. ______" alone is a gap answer line, not the start
    return bool(quick.INLINE_Q_RE.match(s) or quick.OPTIONS_RE.match(s) or quick.LIST_HEAD_RE.match(s)
                or quick.OPT_RE.match(s))


def separate(chunk):
    """Split one part's raw text into (reading text, questions text)."""
    lines = []
    for raw in chunk.splitlines():
        lines.extend(SENTENCE_BEFORE_QUESTION.split(raw))
    passage, questions, started = [], [], False
    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            (questions if started else passage).append("")
            continue
        words = len(s.split())
        if INSTRUCTION_RE.match(s) and words < LONG_LINE_WORDS:
            continue
        is_gap_sentence = bool(GAP_IN_TEXT_RE.search(s)) and words >= 6
        if words >= LONG_LINE_WORDS or is_gap_sentence:
            m = ROMAN_PARAGRAPH_RE.match(s)
            if m:  # "II.  Making your work…" → "2. Making your work…" (questions say "Paragraph 2")
                s = f"{ROMAN[m.group(1)]}. {s[m.end():]}"
            passage.append(s)
            continue
        if not started and _is_question_start(s):
            started = True
        (questions if started else passage).append(s)
    clean = lambda rows: re.sub(r"\n{3,}", "\n\n", "\n".join(rows)).strip()
    return clean(passage), clean(questions)


def _renumber(text, shift, pattern):
    return pattern.sub(lambda m: m.group(0).replace(m.group("n"), str(int(m.group("n")) + shift), 1), text)


Q_NUM_RE = re.compile(r"(?m)^\s*(?P<n>\d{1,3})(?=\s*[.)]\s|\s+\*?[A-Za-z]\s*[).]\s)")
GAP_NUM_RE = re.compile(r"\(?(?P<n>\d{1,3})\)?(?=\s*[.)]?\s*(?:_{2,}|…{2,}|\.{4,}))")


def build(text, section, key_text=""):
    """Parse a whole mock without saving anything. Returns a list of PartDraft."""
    key = quick.parse_key(key_text)
    key_block = "\nANSWERS\n" + "\n".join(f"{n}-{a}" for n, a in sorted(key.items())) if key else ""
    presets = {int(p["code"][1:]): p for p in cefr.structure(section)}
    drafts, last = [], 0
    for num, chunk in sorted(split_parts(text, section).items()):
        preset = presets.get(num)
        if not preset:
            continue
        part = ExamPart(cefr_part=preset["code"], title=preset["title"])
        passage, qtext = separate(chunk)
        # questions for gaps written in the text but not listed below it
        gap_nums = [int(n) for n in re.findall(r"\(?(\d{1,3})\)?\s*[.)]?\s*(?:_{2,}|…{2,}|\.{4,})", passage)]
        listed = {int(m.group("n")) for m in Q_NUM_RE.finditer(qtext)}
        extra = [f"{n}. ______" for n in gap_nums if n not in listed]
        if extra:
            qtext = "\n".join(extra) + ("\n\n" + qtext if qtext else "")
        numbers = sorted({int(m.group("n")) for m in Q_NUM_RE.finditer(qtext)})
        shift = 0
        if numbers and numbers[0] <= last:  # e.g. Part 2 numbered 1–8 instead of 7–14
            shift = last + 1 - numbers[0]
            qtext = _renumber(qtext, shift, Q_NUM_RE)
            passage = _renumber(passage, shift, GAP_NUM_RE)
        items, errors = quick.parse_part(qtext + key_block, part)
        draft = PartDraft(number=num, code=preset["code"], title=preset["title"], passage=passage,
                          questions_text=qtext, items=items, shifted=shift)
        for e in errors:
            (draft.warnings if any(h in e for h in MISSING_ANSWER_HINTS) else draft.errors).append(e)
        if shift:
            draft.warnings.insert(0, f"Question numbers started again from {numbers[0]}; they now continue "
                                     f"from {last + 1}.")
        labels = [l for l, _, _ in (items[0].options if items and items[0].shared else [])]
        if labels and len(labels) >= 3 and all(len(l) == 1 for l in labels):
            gaps = [chr(c) for c in range(ord(labels[0]), ord(labels[-1]) + 1) if chr(c) not in labels]
            if gaps:
                draft.warnings.append(f"Options {', '.join(gaps)} are missing from the list (only "
                                      f"{', '.join(labels)} were found) — check the copied text.")
        drafts.append(draft)
        if items:
            last = max(last, max(it.number for it in items))
    return drafts


@transaction.atomic
def create_mock(section, title, level, time_limit, drafts, user=None):
    """Create the mock with its CEFR parts and save every part that has no blocking errors.
    Returns (exam, {part_pk: questions text} for parts that still need fixing in Quick entry)."""
    exam = MockExam.objects.create(section=section, title=title, level=level or "", time_limit=time_limit,
                                   created_by=user)
    create_cefr_parts(exam)
    unfinished = {}
    for d in drafts:
        part = exam.parts.get(cefr_part=d.code)
        part.passage = quick.normalize_gaps(d.passage, d.gap_numbers) if d.items else d.passage
        part.save(update_fields=["passage"])
        if d.errors:
            unfinished[part.pk] = d.questions_text
        else:
            quick.apply_part(part, d.items)
    return exam, unfinished
