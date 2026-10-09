"""Load the Multilevel (CEFR) practice set: 2 mocks per section + 2 full mocks.

    python manage.py seed_cefr            # create (published) if missing
    python manage.py seed_cefr --replace  # also remove old "Sample …" mocks that have no attempts

Listening audio is generated with the macOS `say` text-to-speech engine and
converted to AAC with `afconvert`. On other systems the listening mocks are
created unpublished without audio — upload recordings in the admin dashboard.
"""
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from exams.models import ExamPart, FullMock, MockExam, Option, Question, SpeakingQuestion, WritingTask

from . import cefr_content as content

RATE = 22050
PAUSE_SECONDS = 0.7


def tts_available():
    return bool(shutil.which("say") and shutil.which("afconvert"))


def synthesize(script, out_path):
    """Render [(voice, text), …] to one AAC file with short pauses between lines."""
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for i, (voice, text) in enumerate(script):
            wav = Path(tmp) / f"{i}.wav"
            subprocess.run(["say", "-v", voice, "-r", "165", f"--data-format=LEI16@{RATE}", "-o", str(wav), text],
                           check=True)
            with wave.open(str(wav)) as w:
                frames.append(w.readframes(w.getnframes()))
        silence = b"\x00\x00" * int(RATE * PAUSE_SECONDS)
        combined = Path(tmp) / "combined.wav"
        with wave.open(str(combined), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(silence.join(frames) + silence)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", str(combined), str(out_path)],
                       check=True)


def draw_town_map(path):
    """Simple original town map for the Part 4 labelling task (letters A–H)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 620), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)
    road = (226, 232, 240)
    # High Street (west–east) and Park Road (north–south, from the park to High Street)
    d.rectangle([40, 300, 860, 370], fill=road)
    d.rectangle([470, 70, 540, 300], fill=road)
    d.text((300, 322), "High Street", fill="#334155", font=font)
    d.text((478, 170), "Park\nRoad", fill="#334155", font=small)
    # Buildings and landmarks
    for box, label in [((60, 400, 220, 470), "Station"), ((170, 200, 340, 270), "Library"),
                       ((640, 400, 800, 470), "Bank"), ((640, 200, 820, 270), "School"),
                       ((380, 22, 630, 62), "PARK (entrance)")]:
        d.rectangle(box, outline="#0f172a", width=3)
        d.text((box[0] + 10, box[1] + 8), label, fill="#0f172a", font=font)
    # Compass
    d.line([(800, 40), (800, 120)], fill="#0f172a", width=3)
    d.line([(760, 80), (840, 80)], fill="#0f172a", width=3)
    for txt, xy in [("N", (793, 12)), ("S", (794, 122)), ("W", (735, 70)), ("E", (846, 70))]:
        d.text(xy, txt, fill="#0f172a", font=small)
    # Letters: A top of Park Road · B west end near station · C outside library · D junction
    # E south side in front of bank · F east end near school · G south side opposite library · H mid Park Road
    letters = {"A": (505, 88), "B": (70, 335), "C": (255, 312), "D": (505, 335), "E": (720, 360),
               "F": (835, 312), "G": (255, 362), "H": (505, 230)}
    for letter, (x, y) in letters.items():
        d.ellipse([x - 17, y - 17, x + 17, y + 17], fill="white", outline="#0f172a", width=3)
        d.text((x - 7, y - 12), letter, fill="#0f172a", font=font)
    img.save(path, "PNG")


def transcript_of(script):
    return "\n".join(f"{voice}: {text}" for voice, text in script)


class Command(BaseCommand):
    help = "Create the Multilevel practice set (2 mocks per section, 2 full mocks)."

    def add_arguments(self, parser):
        parser.add_argument("--replace", action="store_true",
                            help="Remove old 'Sample …' mocks (only those without attempts).")
        parser.add_argument("--draft", action="store_true", help="Create everything unpublished.")

    def handle(self, *args, **opts):
        publish = not opts["draft"]
        if opts["replace"]:
            self._remove_samples()
        made = {"reading": [], "listening": [], "writing": [], "speaking": []}
        for data in content.READING:
            made["reading"].append(self._reading(data, publish))
        for data in content.LISTENING:
            made["listening"].append(self._listening(data, publish))
        for data in content.WRITING:
            made["writing"].append(self._writing(data, publish))
        for data in content.SPEAKING:
            made["speaking"].append(self._speaking(data, publish))
        for i in range(2):
            title = f"Multilevel Full Mock {i + 1:02d}"
            sections = {s: made[s][i] for s in made}
            fm, created = FullMock.objects.get_or_create(title=title, defaults={**sections, "level": "B2"})
            if created:
                fm.is_published = publish and not fm.publish_problems()
                fm.save()
            self.stdout.write(f"{'created' if created else 'exists '}  {title}")
        self.stdout.write(self.style.SUCCESS("Multilevel practice set ready."))

    # ---------------------------------------------------------------- helpers
    def _remove_samples(self):
        for exam in MockExam.objects.filter(title__startswith="Sample "):
            in_full = FullMock.objects.filter(listening=exam) | FullMock.objects.filter(reading=exam) | \
                FullMock.objects.filter(writing=exam) | FullMock.objects.filter(speaking=exam)
            if exam.attempts.exists() or in_full.exists():
                self.stdout.write(f"kept     {exam.title} (has attempts or is in a full mock)")
                continue
            exam.delete()
            self.stdout.write(f"removed  {exam.title}")

    def _existing(self, title, data=None):
        exam = MockExam.objects.filter(title=title).first()
        if exam:
            self.stdout.write(f"exists   {title}")
            if data:
                self._fill_summaries(exam, data)
        return exam

    @staticmethod
    def _fill_summaries(exam, data):
        """Add card topics to mocks created by an earlier version of this command."""
        if data.get("summary") and not exam.summary:
            exam.summary = data["summary"]
            exam.save(update_fields=["summary"])
        for order, p in enumerate(data.get("parts", []), start=1):
            exam.parts.filter(order=order, summary="").update(summary=p.get("summary", ""))
        for order, text in enumerate(data.get("task_summaries", []), start=1):
            exam.writing_tasks.filter(order=order, summary="").update(summary=text)
        for part, text in data.get("summaries", {}).items():
            first = exam.speaking_questions.filter(part=part).order_by("order").first()
            if first and not first.summary:
                first.summary = text
                first.save(update_fields=["summary"])

    @transaction.atomic
    def _reading(self, data, publish):
        exam = self._existing(data["title"], data)
        if exam:
            return exam
        exam = MockExam.objects.create(title=data["title"], section="reading", level=data["level"],
                                       time_limit=data["time_limit"], instructions=data["instructions"])
        number = 1
        for order, p in enumerate(data["parts"], start=1):
            part = ExamPart.objects.create(exam=exam, title=p["title"], order=order, instructions=p["instructions"],
                                           passage=p["passage"], summary=p.get("summary", ""))
            number = self._questions(part, p, number)
        exam.is_published = publish
        exam.save()
        self.stdout.write(f"created  {exam.title}")
        return exam

    def _questions(self, part, p, number):
        for qtype, prompt, answer in p.get("questions", []):
            q = Question.objects.create(part=part, order=number, question_type=qtype, prompt=prompt,
                                        correct_answer=answer)
            for i, (label, text) in enumerate(p.get("options", []) if qtype in ("matching", "headings", "map_labelling") else []):
                Option.objects.create(question=q, label=label, text=text, order=i)
            number += 1
        for prompt, answer in p.get("notes", []):
            Question.objects.create(part=part, order=number, question_type="gap_filling", prompt=prompt,
                                    correct_answer=answer)
            number += 1
        for prompt, options in p.get("mcq", []):
            q = Question.objects.create(part=part, order=number, question_type="multiple_choice", prompt=prompt)
            for i, (label, text, ok) in enumerate(options):
                Option.objects.create(question=q, label=label, text=text, is_correct=ok, order=i)
            number += 1
        return number

    def _listening(self, data, publish):
        exam = self._existing(data["title"], data)
        if exam:
            self._add_missing_parts(exam, data)
            return exam
        with transaction.atomic():
            exam = MockExam.objects.create(
                title=data["title"], section="listening", level=data["level"], time_limit=data["time_limit"],
                instructions=data["instructions"],
                transcript="\n\n".join(f"{p['title']}\n{transcript_of(p['script'])}" for p in data["parts"]))
            number = 1
            parts = []
            for order, p in enumerate(data["parts"], start=1):
                part = ExamPart.objects.create(exam=exam, title=p["title"], order=order, summary=p.get("summary", ""),
                                               instructions=p["instructions"], transcript=transcript_of(p["script"]))
                number = self._questions(part, p, number)
                parts.append((part, p))
                self._map_image(part, p)
        if tts_available():
            with tempfile.TemporaryDirectory() as tmp:
                for part, p in parts:
                    path = Path(tmp) / f"part{part.order}.m4a"
                    synthesize(p["script"], path)
                    with open(path, "rb") as fh:
                        part.audio.save(f"{exam.pk}-part{part.order}.m4a", File(fh), save=True)
            exam.is_published = publish
            exam.save()
            self.stdout.write(f"created  {exam.title} (audio generated)")
        else:
            self.stdout.write(self.style.WARNING(
                f"created  {exam.title} WITHOUT audio (no text-to-speech here) — upload audio, then publish"))
        return exam

    @staticmethod
    def _map_image(part, p):
        if not p.get("map") or part.image:
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.png"
            draw_town_map(path)
            with open(path, "rb") as fh:
                part.image.save(f"town-map-{part.pk}.png", File(fh), save=True)

    def _add_missing_parts(self, exam, data):
        """Parts added to the content after this mock was first created (e.g. the map task)."""
        existing = set(exam.parts.values_list("order", flat=True))
        number = (Question.objects.filter(exam=exam).order_by("-order").values_list("order", flat=True).first()
                  or 0) + 1
        for order, p in enumerate(data["parts"], start=1):
            if order in existing:
                continue
            with transaction.atomic():
                part = ExamPart.objects.create(exam=exam, title=p["title"], order=order, summary=p.get("summary", ""),
                                               instructions=p["instructions"], transcript=transcript_of(p["script"]))
                number = self._questions(part, p, number)
            self._map_image(part, p)
            if tts_available():
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / f"part{order}.m4a"
                    synthesize(p["script"], path)
                    with open(path, "rb") as fh:
                        part.audio.save(f"{exam.pk}-part{order}.m4a", File(fh), save=True)
            exam.transcript = (exam.transcript + f"\n\n{p['title']}\n{transcript_of(p['script'])}").strip()
            exam.save(update_fields=["transcript"])
            self.stdout.write(f"added    {p['title']} to {exam.title}")

    @transaction.atomic
    def _writing(self, data, publish):
        exam = self._existing(data["title"], data)
        if exam:
            return exam
        exam = MockExam.objects.create(title=data["title"], section="writing", level=data["level"],
                                       time_limit=data["time_limit"], instructions=data["instructions"],
                                       summary=data.get("summary", ""))
        summaries = data.get("task_summaries", [])
        for order, (ttype, title, low, high, minutes, text) in enumerate(data["tasks"], start=1):
            topic = f"{data['situation']}\n\n{text}" if ttype != "task2" else text
            WritingTask.objects.create(exam=exam, order=order, title=title, task_type=ttype, topic=topic,
                                       minimum_word_count=low, maximum_word_count=high, time_limit=minutes,
                                       level=data["level"],
                                       summary=summaries[order - 1] if order <= len(summaries) else "")
        exam.is_published = publish
        exam.save()
        self.stdout.write(f"created  {exam.title}")
        return exam

    @transaction.atomic
    def _speaking(self, data, publish):
        exam = self._existing(data["title"], data)
        if exam:
            return exam
        exam = MockExam.objects.create(title=data["title"], section="speaking", level=data["level"],
                                       time_limit=data["time_limit"],
                                       instructions="8 questions in four parts. Each answer is recorded after a "
                                                    "short preparation time.")
        counters = {}
        for part, question, cue, prep, speak in data["questions"]:
            counters[part] = counters.get(part, 0) + 1
            SpeakingQuestion.objects.create(
                exam=exam, part=part, order=counters[part], question=question, cue_card_points=cue,
                preparation_time=prep, speaking_time=speak,
                summary=data.get("summaries", {}).get(part, "") if counters[part] == 1 else "")
        exam.is_published = publish
        exam.save()
        self.stdout.write(f"created  {exam.title}")
        return exam
