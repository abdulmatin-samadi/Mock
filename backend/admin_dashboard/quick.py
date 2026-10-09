"""Quick entry: paste a whole part / speaking set / writing set as plain text.

Reading & Listening part format (one question per numbered line, answer after "="):

    1. ______ = library | libraries          gap filling (accepted answers split by |)
    5. The club opened in 1998. = TRUE       True / False / No Information
    7. What is the writer's main purpose?    multiple choice: own options below,
    A) to inform                             the correct one marked with *
    *B) to persuade
    OPTIONS                                  one shared list for matching / headings / map
    A) Weekend Photography
    6. Aziz works in an office… = C

`OPTIONS: A-I` is a shortcut for a map with letters A to I and no text.
"""
import re
from dataclasses import dataclass, field

from django.db import transaction

from exams import cefr
from exams.models import Option, Question, SpeakingQuestion, WritingTask

TFNG = Question.FIXED_CHOICES[Question.Type.TFNG]
Q_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.*)$")
OPT_RE = re.compile(r"^\s*(\*)?\s*([A-Za-z]|[ivxIVX]{1,5})\s*[).]\s*(.*)$")
# PDF copies often lose the dot: "A<tab>THE ACE HOTEL" or "A    THE ACE HOTEL"
# In matching / headings / map parts also "A – text", "A: text", "A text" (short lines only)
OPT_LOOSE_RE = re.compile(r"^\s*(\*)?\s*([A-J])(?:\s*[-–—:]\s*|\s+)(\S.*)$")
# Cyrillic letters that look like Latin ones (Word documents typed with an Uzbek/Russian keyboard)
HOMOGLYPHS = str.maketrans("АВСЕНІКМОРТХаеосрх", "ABCEHIKMOPTXaeocpx")
OPT_TAB_RE = re.compile(r"^\s*(\*)?\s*([A-J])(?:\t|\s{2,})\s*(\S.*)$")
# headings that introduce the list of options in printed papers
LIST_HEAD_RE = re.compile(r"^\s*(list of headings|headings|list of (statements|people|places|options)|topic\b.*)\s*:?.*$", re.I)
OPTIONS_RE = re.compile(r"^\s*(options|variantlar)\s*:?\s*(.*)$", re.I)
RANGE_RE = re.compile(r"^([A-Za-z])\s*[-–]\s*([A-Za-z])$")
# "1   A) Please." — question number and its first option on one line (Listening Part 1 papers)
INLINE_Q_RE = re.compile(r"^\s*(\d{1,3})\s+(\*?\s*[A-Za-z]\s*[).]\s.*)$")
# Answer key written after the questions: "ANSWERS: 1-B 2-A 3 C" (also "KEYS" / "JAVOBLAR")
# a whole word followed by ":" / a number / end of line — so "Keyless room entry" is not an answer key
KEY_HEAD_RE = re.compile(r"^\s*(answers?|answer key|keys?|javoblar|kalit)\b\s*(?::|(?=\d)|$)\s*(.*)$", re.I)
KEY_PAIR_RE = re.compile(r"(\d{1,3})\s*[-–.:)=]?\s*(NOT GIVEN|NO INFORMATION|TRUE|FALSE|NG|NI|[ivx]{2,5}|[A-Za-z])(?![A-Za-z])", re.I)
PART_HEAD_RE = re.compile(r"^\s*part\s*\d+(\.\d+)?\s*[:.]?\s*$", re.I)
ANSWER_SPLIT = re.compile(r"\s+=\s*(?=[^=]*$)")


@dataclass
class Item:
    number: int
    prompt: str
    answer: str = ""
    options: list = field(default_factory=list)  # [(label, text, is_correct)]
    shared: bool = False
    qtype: str = ""
    line: int = 0
    block: int = -1  # index of the OPTIONS list written before this question
    tfng: bool = False  # printed with "A) True B) False C) No Information" options

    @property
    def answer_display(self):
        return self.answer.replace("|", " / ")


INLINE_OPT_SPLIT = re.compile(r"(?<=\S)\s+(?=\*?[A-D]\)\s)")
MULTI_Q_SPLIT = re.compile(r"(?:\t|\s{2,})(?=\d{1,3}\.\s)|(?<=\S)\s*\t(?=[A-J]\t)")  # also "… \tA\ta musician"
KEY_WORD_RE = re.compile(r"(\d{1,3})\s*[-–.:)=]\s*([^,;]+?)(?=\s+\d{1,3}\s*[-–.:)=]|\s*[,;]|\s*$)")
TFNG_TEXTS = {"TRUE", "FALSE", "NO INFORMATION", "NOT GIVEN"}


def expand_lines(text):
    """Split printed layouts into one item per line: "C) x    D) y" → two options,
    "15. Paragraph 1   17. Paragraph 3" → two questions."""
    out = []
    for raw in (text or "").splitlines():
        raw = re.sub(r"^(\s*\*?\s*)([АВСЕНІКМОРТХ])(?=[\s).:–—-])", lambda m: m.group(1) + m.group(2).translate(HOMOGLYPHS), raw)
        for piece in MULTI_Q_SPLIT.split(raw):
            if not re.search(r"\S\s+\*?[A-D]\)\s", piece):
                out.append(piece)
                continue
            parts = INLINE_OPT_SPLIT.split(piece)
            if len(parts) > 1 and re.fullmatch(r"\s*\d{1,3}", parts[0]):
                parts = [f"{parts[0]} {parts[1]}"] + parts[2:]  # "1  A) Please." stays a question line
            out.extend(parts)
    return out


def parse_key(text):
    """Answer key text → {number: answer}. Accepts "1-C 2-A", "3 B", "1. shop, 2. name | names"."""
    key = {}
    for line in (text or "").splitlines():
        line = KEY_HEAD_RE.sub(lambda m: m.group(2), line) if KEY_HEAD_RE.match(line) else line
        found = KEY_WORD_RE.findall(line)
        if not found:
            found = KEY_PAIR_RE.findall(line)
        for num, ans in found:
            ans = ans.strip().strip(".")
            if ans and ans != "?":
                key[int(num)] = ans
    return key


def _is_roman(label):
    return bool(re.fullmatch(r"[ivx]{1,5}", label))


def parse_part(text, part):
    """Turn pasted text into question items for `part`. Returns (items, errors)."""
    preset = cefr.PARTS.get(part.cefr_part or "")
    allowed = preset["types"] if preset else None
    # matching / headings / map parts: every lettered line belongs to the shared list of options
    label_only = bool(allowed) and all(t in Question.LABEL_TYPES for t in allowed)
    items, errors, blocks = [], [], []
    current, in_shared = None, False
    key, in_key = {}, False
    for n, raw in enumerate(expand_lines(text), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if label_only and LIST_HEAD_RE.match(line) and not Q_RE.match(line):
            in_shared, current = True, None
            blocks.append([])
            continue
        m = OPTIONS_RE.match(line)
        if m:
            in_shared, current = True, None
            rest = m.group(2).strip()
            rng = RANGE_RE.match(rest)
            if rng:
                a, b = rng.group(1).upper(), rng.group(2).upper()
                blocks.append([(chr(c), "", False) for c in range(ord(a), ord(b) + 1)])
            else:
                blocks.append([(tok.upper(), "", False) for tok in re.split(r"[\s,]+", rest) if tok])
            continue
        if PART_HEAD_RE.match(line):
            continue
        m = KEY_HEAD_RE.match(line)
        if m or in_key:
            in_key = True
            key.update(parse_key(line))
            continue
        m = INLINE_Q_RE.match(line)
        if m:
            in_shared = False
            current = Item(number=int(m.group(1)), prompt="", line=n, block=len(blocks) - 1)
            items.append(current)
            line = m.group(2)  # handled below as the question's first option
        m = None if current is not None and current.line == n else Q_RE.match(line)
        if m:
            in_shared = False
            body = m.group(2).strip()
            parts = ANSWER_SPLIT.split(body, maxsplit=1)
            prompt, answer = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (body, "")
            if body.startswith("="):
                prompt, answer = "", body[1:].strip()
            current = Item(number=int(m.group(1)), prompt=prompt, answer=answer, line=n, block=len(blocks) - 1)
            items.append(current)
            continue
        m = OPT_RE.match(line) or OPT_TAB_RE.match(line)
        if not m and label_only and not Q_RE.match(line) and len(line.split()) <= 12:
            loose = OPT_LOOSE_RE.match(line)
            # a new list may start after the questions, but only with "A"
            if loose and (in_shared or current is None or loose.group(2) == "A"):
                m = loose
        if m and label_only and not in_shared:
            in_shared, current = True, None  # an option list written without the word OPTIONS
            blocks.append([])
        if m and (in_shared or current is not None):
            label = m.group(2)
            # lowercase roman numerals (i, ii, iv …) are heading labels; everything else is a capital letter
            option = (label if re.fullmatch(r"[ivx]+", label) else label.upper(), m.group(3).strip(), bool(m.group(1)))
            if in_shared:
                blocks[-1].append(option)
            else:
                current.options.append(option)
            continue
        # A line that is neither: continuation of the previous prompt / option text.
        if in_shared and blocks and blocks[-1]:
            label, text_, ok = blocks[-1][-1]
            blocks[-1][-1] = (label, f"{text_} {line.strip()}".strip(), ok)
        elif current is not None and current.options:
            label, text_, ok = current.options[-1]
            current.options[-1] = (label, f"{text_} {line.strip()}".strip(), ok)
        elif current is not None:
            current.prompt = f"{current.prompt} {line.strip()}".strip()
        elif not items and not blocks:
            continue  # instructions written before the first question (e.g. "Each recording is played twice")
        else:
            errors.append(f"Line {n}: “{line.strip()[:60]}” is not a question. Start questions with a number, e.g. “1. …”.")

    for it in items:
        k = key.get(it.number)
        if k and not it.answer and not any(ok for _, _, ok in it.options):
            it.answer = k if re.fullmatch(r"[ivx]+|.*[a-z].*\s.*|[a-z]{2,}.*", k) else k.upper()
        # "A) True  B) False  C) No Information" printed as options → a True/False/No Information question
        if it.options and {Question.canonical_choice(t.strip(" .")) for _, t, _ in it.options} <= TFNG_TEXTS | {"NO INFORMATION"} \
                and len(it.options) in (2, 3) and (not allowed or Question.Type.TFNG in allowed):
            ans = it.answer.strip().upper()
            chosen = next((t for l, t, ok in it.options if ok or l.upper() == ans), "")
            it.answer = Question.canonical_choice(chosen.strip(" .")) if chosen else (ans if ans in TFNG else "")
            it.options = []
            it.tfng = True
            if not it.answer:
                errors.append(f"Question {it.number}: add the answer (TRUE, FALSE or NO INFORMATION).")
    seen = set()
    for it in items:
        shared = blocks[max(it.block, 0)] if blocks else []
        shared_labels = {l.upper() for l, _, _ in shared}
        if it.number in seen:
            errors.append(f"Line {it.line}: question {it.number} appears twice.")
        seen.add(it.number)
        ans_upper = re.sub(r"\s+", " ", it.answer.upper()).strip()
        if it.tfng:
            it.qtype = Question.Type.TFNG
        elif it.options:
            it.qtype = Question.Type.MULTIPLE_CHOICE
            if ans_upper and not any(ok for _, _, ok in it.options):
                it.options = [(l, t, l.upper() == ans_upper) for l, t, _ in it.options]
            if len(it.options) < 2:
                errors.append(f"Question {it.number}: multiple choice needs at least two options (A, B …).")
            if sum(ok for _, _, ok in it.options) != 1:
                errors.append(f"Question {it.number}: mark exactly one correct option with * (e.g. “*B) …”) "
                              f"or write “= B” after the question.")
            it.answer = ""
        elif shared and ans_upper in shared_labels:
            it.shared = True
            if (part.cefr_part == "R3" or any(_is_roman(l) for l, _, _ in shared)
                    or re.match(r"paragraph\b", it.prompt, re.I)):
                it.qtype = Question.Type.HEADINGS
            elif part.cefr_part == "L4" or (part.image and not any(t for _, t, _ in shared)):
                it.qtype = Question.Type.MAP_LABELLING
            else:
                it.qtype = Question.Type.MATCHING
            it.options = list(shared)
            it.answer = next(l for l, _, _ in shared if l.upper() == ans_upper)
        elif Question.canonical_choice(ans_upper) in TFNG and (not allowed or Question.Type.TFNG in allowed):
            it.qtype = Question.Type.TFNG
            it.answer = Question.canonical_choice(ans_upper)
        elif label_only and not shared:
            it.qtype = allowed[0]
            errors.append(f"Question {it.number}: the list of options is missing. Write it before the questions, "
                          f"one per line: “A) …”, “B) …” (or under the word OPTIONS).")
        elif shared and allowed and Question.Type.GAP_FILLING not in allowed:
            # matching / headings / map part, but the answer is missing or not a label
            it.qtype = next(t for t in allowed if t in Question.LABEL_TYPES)
            labels = [l for l, _, _ in shared]
            span = f"{labels[0]}–{labels[-1]}" if len(labels) > 1 else labels[0]
            it.options, it.shared, it.answer = list(shared), True, ""  # keep the list so the answer can be added later
            errors.append(f"Question {it.number}: after “=” write one of the OPTIONS letters ({span}), "
                          f"e.g. “{it.number}. {it.prompt[:20] or 'Paragraph 1'} = {labels[0]}”.")
        else:
            it.qtype = Question.Type.GAP_FILLING
            # "3. healthier" with no "=": a short line in a gap-filling part is the answer itself.
            gap_part = not allowed or Question.Type.GAP_FILLING in allowed
            if (not it.answer and gap_part and it.prompt and not it.prompt.rstrip().endswith("?")
                    and not re.search(r"_{2,}", it.prompt) and len(it.prompt.split()) <= 4):
                it.answer, it.prompt = it.prompt, ""
            it.answer = " | ".join(a.strip() for a in re.split(r"\||\s/\s", it.answer) if a.strip()).replace(" | ", "|")
            if not it.answer:
                errors.append(f"Question {it.number}: write the answer, e.g. “{it.number}. library”.")
            if shared and re.fullmatch(r"[A-Za-z]|[ivx]{1,5}", it.answer.strip()):
                errors.append(f"Question {it.number}: answer “{it.answer}” is not one of the OPTIONS labels.")
        if not it.prompt or re.fullmatch(r"[_\s.…]*", it.prompt):
            it.prompt = f"Gap {it.number}" if it.qtype == Question.Type.GAP_FILLING else it.prompt
        if not it.prompt and it.qtype == Question.Type.MULTIPLE_CHOICE:
            it.prompt = "Choose the correct answer."  # e.g. Listening Part 1: the question is only in the audio
        if not it.prompt:
            errors.append(f"Question {it.number}: the question text is empty.")
        if allowed and it.qtype not in allowed:
            label = dict(Question.Type.choices)[it.qtype]
            errors.append(f"Question {it.number}: {label} is not used in {preset['title']}.")
    if not items and not errors:
        errors.append("No questions found. Write the questions in box 2, one numbered line each (e.g. “7. Emma … = C”). "
                      "For gap filling just mark the gaps in the text as “1. ______” — the questions are added for you.")
    return items, errors


# a gap: number + a line of underscores, dots or "…" ("9. ______", "(9) ……………", "30 ........")
GAP_ANY_RE = re.compile(r"(?<![\w(])\(?(\d{1,3})\)?\s*[.)]?\s*(?:_{2,}|…{2,}|\.{4,})[_….]*")


# Errors that only mean "the answer is not written yet": the part can still be saved
# (publishing stays blocked until every question has its answer).
MISSING_ANSWER_HINTS = ("write the answer", "mark exactly one correct option", "write one of the OPTIONS letters",
                        "add the answer (TRUE")
GAP_NUMBER_RE = re.compile(r"\(?(\d{1,3})\)?\s*[.)]?\s*(?:_{2,}|…{2,}|\.{4,})")


def split_errors(errors):
    """(blocking errors, missing-answer warnings)."""
    warn = [e for e in errors if any(h in e for h in MISSING_ANSWER_HINTS)]
    return [e for e in errors if e not in warn], warn


def add_gap_questions(passage, text):
    """Questions for gaps written in the text ("1.______") that are not listed in the questions box."""
    listed = {int(m.group(1)) for m in re.finditer(r"(?m)^\s*(\d{1,3})(?=\s*[.)]\s|\s+\*?[A-Za-z]\s*[).]\s)", text or "")}
    gaps = []
    for n in GAP_NUMBER_RE.findall(passage or ""):
        if int(n) not in listed and f"{int(n)}. ______" not in gaps:
            gaps.append(f"{int(n)}. ______")
    return ("\n".join(gaps) + ("\n\n" + text if (text or "").strip() else "")) if gaps else text


def pull_options(passage):
    """Lettered option blocks ("A. THE ACE HOTEL" + its short lines) written in the text box of a
    matching part → (text without them, options text). Long paragraphs stay in the text."""
    keep, opts, in_opt = [], [], False
    for line in (passage or "").splitlines():
        s = line.strip()
        m = (OPT_RE.match(s) or OPT_TAB_RE.match(s)) if s else None
        if m and len(s.split()) < 30:  # long lines ("I. The overriding idea …") are paragraphs, not options
            opts.append(f"{m.group(2).upper()}) {m.group(3).strip()}")
            in_opt = True
        elif in_opt and s and len(s.split()) < 30:
            opts.append(s)  # "Boutique hotel", "Pool, bar …" belong to the option above
        else:
            in_opt = False
            keep.append(line)
    return "\n".join(keep).strip(), "\n".join(opts)


def normalize_gaps(passage, numbers):
    """Turn "1. ______", "2.______", "3) ___" or "(4)____" into the "(4) ______" marker the exam room uses."""
    def repl(m):
        return f"({m.group(1)}) ______" if int(m.group(1)) in numbers else m.group(0)
    return GAP_ANY_RE.sub(repl, passage or "")


def missing_gaps(passage, items):
    """Gap-filling question numbers that have no "(N) ______" marker in the text."""
    found = {int(n) for n in re.findall(r"\((\d+)\)\s*_{2,}", passage or "")}
    return [it.number for it in items if it.qtype == Question.Type.GAP_FILLING and it.number not in found]


def serialize_part(part):
    """Existing questions back to the quick-entry text (so the page can be edited again)."""
    questions = list(part.questions.prefetch_related("options"))
    lines, shared_written = [], None
    for q in questions:
        opts = list(q.options.all())
        if q.question_type in Question.LABEL_TYPES:
            key = tuple((o.label, o.text) for o in opts)
            if key != shared_written:
                if q.question_type == Question.Type.MAP_LABELLING and not any(o.text for o in opts) and opts:
                    lines += ["", f"OPTIONS: {opts[0].label}-{opts[-1].label}"]
                else:
                    lines += ["", "OPTIONS"] + [f"{o.label}) {o.text}" for o in opts]
                lines.append("")
                shared_written = key
            lines.append(f"{q.order}. {q.prompt} = {q.correct_answer}")
        elif q.question_type == Question.Type.MULTIPLE_CHOICE:
            lines.append(f"{q.order}. {q.prompt}")
            lines += [f"{'*' if o.is_correct else ''}{o.label}) {o.text}" for o in opts]
            lines.append("")
        else:
            answer = q.correct_answer.replace("|", " | ")
            if re.fullmatch(r"Gap \d+", q.prompt) and len(q.correct_answer.replace("|", " ").split()) <= 4:
                lines.append(f"{q.order}. {answer}")  # the short form an admin naturally types
            else:
                prompt = "______" if re.fullmatch(r"Gap \d+", q.prompt) else q.prompt
                lines.append(f"{q.order}. {prompt} = {answer}")
    return "\n".join(lines).strip()


def part_locked(part):
    """Students already answered these questions -> replacing them would delete their answers."""
    from results.models import Answer

    return Answer.objects.filter(question__part=part).exists()


@transaction.atomic
def apply_part(part, items):
    part.questions.all().delete()
    for it in sorted(items, key=lambda i: i.number):
        q = Question.objects.create(part=part, order=it.number, question_type=it.qtype, prompt=it.prompt,
                                    correct_answer=it.answer)
        Option.objects.bulk_create([Option(question=q, label=l, text=t, is_correct=ok, order=i)
                                    for i, (l, t, ok) in enumerate(it.options)])
    return len(items)


# ------------------------------------------------------------------ speaking
SPEAKING_HEAD = re.compile(r"^\s*part\s*(1\.1|1\.2|2|3)\s*:?\s*$", re.I)
SPEAKING_PARTS = {"1.1": 1, "1.2": 2, "2": 3, "3": 4}


def parse_speaking(text):
    """PART 1.1 / PART 1.2 / PART 2 / PART 3 headings; one question per line.
    Part 2 bullet points start with "-"; Part 3 arguments start with "For:" / "Against:"."""
    items, errors, part = [], [], None
    for n, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        m = SPEAKING_HEAD.match(line)
        if m:
            part = SPEAKING_PARTS[m.group(1)]
            continue
        if part is None:
            errors.append(f"Line {n}: start with a heading such as “PART 1.1”.")
            continue
        is_point = line[:1] in "-•*" or re.match(r"^(for|against)\s*:", line, re.I)
        if is_point and part in (3, 4):
            if not items or items[-1]["part"] != part:
                errors.append(f"Line {n}: write the Part {'2' if part == 3 else '3'} question before its points.")
                continue
            point = line.lstrip("-•* ").strip()
            if part == 4:
                point = re.sub(r"^(for|against)\s*:\s*", lambda mm: mm.group(1).capitalize() + ": ", point, flags=re.I)
            items[-1]["cue"].append(point)
            continue
        items.append({"part": part, "question": re.sub(r"^\d+\s*[.)]\s*", "", line), "cue": [], "line": n})
    counts = {p: sum(1 for i in items if i["part"] == p) for p in (1, 2, 3, 4)}
    if not items:
        errors.append("No questions found. Use headings PART 1.1, PART 1.2, PART 2, PART 3.")
    if items and counts[4] and not any(c.startswith(("For:", "Against:")) for i in items if i["part"] == 4
                                       for c in i["cue"]):
        errors.append("Part 3: add the arguments as lines starting with “For:” and “Against:”.")
    return items, errors, counts


def serialize_speaking(exam):
    lines, last = [], None
    labels = {v: k for k, v in SPEAKING_PARTS.items()}
    for q in exam.speaking_questions.order_by("part", "order"):
        if q.part != last:
            lines += (["", f"PART {labels[q.part]}"] if lines else [f"PART {labels[q.part]}"])
            last = q.part
        lines.append(q.question)
        for point in q.cue_points if hasattr(q, "cue_points") else q.cue_card_points.splitlines():
            point = point.strip()
            if point:
                lines.append(point if q.part == 4 else f"- {point}")
    return "\n".join(lines).strip()


def speaking_locked(exam):
    return exam.speaking_questions.filter(submissions__isnull=False).exists()


@transaction.atomic
def apply_speaking(exam, items, image=None):
    old_image = exam.speaking_questions.filter(part=2).exclude(image="").values_list("image", flat=True).first()
    exam.speaking_questions.all().delete()
    counters = {}
    for it in items:
        counters[it["part"]] = counters.get(it["part"], 0) + 1
        first = counters[it["part"]] == 1
        prep, speak = SpeakingQuestion.DEFAULT_TIMES[it["part"]] if first or it["part"] != 2 else (5, 30)
        q = SpeakingQuestion(exam=exam, part=it["part"], order=counters[it["part"]], question=it["question"],
                             cue_card_points="\n".join(it["cue"]), preparation_time=prep, speaking_time=speak)
        if it["part"] == 2 and first:
            if image:
                q.image = image
            elif old_image:
                q.image.name = old_image
        q.save()
    return len(items)


# ------------------------------------------------------------------ writing
WRITING_HEAD = re.compile(r"^\s*task\s*(1\.1|1\.2|2)\s*:?\s*$", re.I)
WRITING_DEFAULTS = {
    "1.1": (WritingTask.TaskType.TASK1_1, "Task 1.1", 50, 70, 15),
    "1.2": (WritingTask.TaskType.TASK1_2, "Task 1.2", 120, 150, 20),
    "2": (WritingTask.TaskType.TASK2, "Task 2", 180, 200, 25),
}


def parse_writing(text):
    """SITUATION (optional, shared by Task 1.1 and 1.2), then TASK 1.1 / TASK 1.2 / TASK 2 blocks."""
    blocks, current, situation, errors = {}, None, [], []
    for raw in (text or "").splitlines():
        m = WRITING_HEAD.match(raw)
        if m:
            current = m.group(1)
            blocks[current] = []
            continue
        if re.match(r"^\s*(situation|vaziyat)\s*:?\s*$", raw, re.I):
            current = "situation"
            continue
        if current == "situation":
            situation.append(raw)
        elif current:
            blocks[current].append(raw)
        elif raw.strip():
            situation.append(raw)
    situation = "\n".join(situation).strip()
    items = []
    for key in ("1.1", "1.2", "2"):
        body = "\n".join(blocks.get(key, [])).strip()
        if not body:
            continue
        ttype, title, low, high, minutes = WRITING_DEFAULTS[key]
        topic = f"{situation}\n\n{body}" if situation and key != "2" else body
        items.append({"key": key, "task_type": ttype, "title": title, "topic": topic, "low": low, "high": high,
                      "minutes": minutes})
    if not items:
        errors.append("No tasks found. Use the headings TASK 1.1, TASK 1.2 and TASK 2.")
    return items, errors, situation


def serialize_writing(exam):
    tasks = list(exam.writing_tasks.order_by("order"))
    if not tasks:
        return ""
    keys = {v[0]: k for k, v in WRITING_DEFAULTS.items()}
    t1 = [t for t in tasks if t.task_type != WritingTask.TaskType.TASK2]
    situation = ""
    if len(t1) == 2:
        a, b = t1[0].topic.split("\n\n"), t1[1].topic.split("\n\n")
        if len(a) > 1 and len(b) > 1 and a[0] == b[0]:
            situation = a[0]
    lines = ["SITUATION", situation, ""] if situation else []
    for t in tasks:
        topic = t.topic[len(situation):].lstrip("\n") if situation and t.topic.startswith(situation) else t.topic
        lines += [f"TASK {keys.get(t.task_type, '2')}", topic, ""]
    return "\n".join(lines).strip()


def writing_locked(exam):
    return exam.writing_tasks.filter(submissions__isnull=False).exists()


@transaction.atomic
def apply_writing(exam, items):
    exam.writing_tasks.all().delete()
    for order, it in enumerate(items, start=1):
        WritingTask.objects.create(exam=exam, order=order, title=it["title"], task_type=it["task_type"],
                                   topic=it["topic"], minimum_word_count=it["low"], maximum_word_count=it["high"],
                                   time_limit=it["minutes"], level=exam.level or "")
    return len(items)
