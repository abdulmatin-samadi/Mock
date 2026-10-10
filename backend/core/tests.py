"""End-to-end tests for the platform. AI providers are replaced by test doubles
(no network); everything else — grading, permissions, persistence — is real."""
import json
import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from exams import scoring
from exams.models import ExamPart, MockExam, Option, Question, SpeakingQuestion, WritingTask
from results.models import ExamAttempt
from speaking.models import SpeakingSubmission
from writing.models import WritingSubmission

TMP_MEDIA = tempfile.mkdtemp()
PASSWORD = "Str0ng-pass-123"


class FakeLLM:
    name = "fake"
    model = "fake-model"
    supports_audio_pronunciation = False

    def __init__(self, score=50):
        self.score = score
        self.calls = []

    def generate_json(self, *, system, prompt, schema, schema_name):
        self.calls.append(schema_name)
        self.systems = getattr(self, "systems", []) + [system]
        if schema_name == "answer_explanation":
            return {"explanation": "The text says it directly."}
        s = self.score
        base = {"overall_score": s, "cefr_level": "B2", "detailed_feedback": "Solid answer.",
                "improvement_suggestions": ["Use more linking words."], "grammar_feedback": "ok",
                "vocabulary_feedback": "ok", "coherence_feedback": "ok"}
        if schema_name == "writing_evaluation":
            return {**base, "task_score": s, "coherence_score": s, "vocabulary_score": s + 1, "grammar_score": s - 1,
                    "task_feedback": "ok",
                    "grammar_mistakes": [{"original": "He go", "correction": "He goes", "explanation": "agreement"}],
                    "vocabulary_mistakes": [], "suggested_corrections": [], "weak_sentences": [],
                    "strong_sentences": [{"sentence": "x", "reason": "y"}]}
        return {**base, "fluency_score": s, "vocabulary_score": s, "grammar_score": s, "fluency_feedback": "ok",
                "mistakes": []}


class FakeSTT:
    name = "fake-stt"
    model = "fake-whisper"

    def transcribe(self, *, data, filename, content_type):
        assert data.startswith(b"\x1a\x45\xdf\xa3")
        return "I usually spend my weekends with my family in the countryside."


def make_user(email, role=User.Role.STUDENT, **kw):
    return User.objects.create_user(email=email, password=PASSWORD, first_name=email.split("@")[0].title(),
                                    last_name="Test", role=role, **kw)


@override_settings(MEDIA_ROOT=TMP_MEDIA, PRIVATE_MEDIA_ROOT=TMP_MEDIA, AI_TASK_MODE="sync", LANGUAGE_CODE="en",
                   STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "private": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                                         "OPTIONS": {"location": TMP_MEDIA}},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class BaseTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.student = make_user("student@example.com")
        self.other = make_user("other@example.com")
        self.admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD,
                                                   first_name="Ad", last_name="Min")

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def web(self, user):
        self.client.force_login(user)
        return self.client


class ScoringTests(TestCase):
    def test_rounding_and_cefr(self):
        self.assertEqual(scoring.round_score(50.5), Decimal("51"))
        self.assertEqual(scoring.round_score(50.25), Decimal("50"))
        self.assertEqual(scoring.multilevel_to_cefr(65), "C1")
        self.assertEqual(scoring.multilevel_to_cefr(51), "B2")
        self.assertEqual(scoring.multilevel_to_cefr(38), "B1")
        self.assertEqual(scoring.multilevel_to_cefr(37), "Below B1")
        self.assertEqual(scoring.percentage_to_multilevel(Decimal("100")), 75)

    def test_text_matching(self):
        self.assertTrue(scoring.text_matches("  The Library. ", "library|libraries"))
        self.assertTrue(scoring.text_matches("1,000", "1000"))
        self.assertFalse(scoring.text_matches("", "x"))
        self.assertFalse(scoring.text_matches("museum", "library"))


class ObjectiveExamTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.exam = MockExam.objects.create(title="Multilevel Mock #4", section="reading",
                                            time_limit=60, is_published=True)
        part = ExamPart.objects.create(exam=self.exam, title="Passage 1", passage="Text", order=1)
        self.q_mcq = Question.objects.create(part=part, order=1, question_type="multiple_choice", prompt="Pick")
        self.opt_ok = Option.objects.create(question=self.q_mcq, label="A", text="right", is_correct=True)
        self.opt_bad = Option.objects.create(question=self.q_mcq, label="B", text="wrong")
        self.q_tf = Question.objects.create(part=part, order=2, question_type="true_false_not_given", prompt="TF",
                                            correct_answer="NOT GIVEN")
        self.q_gap = Question.objects.create(part=part, order=3, question_type="gap_filling", prompt="Gap",
                                             correct_answer="library|libraries")
        self.q_match = Question.objects.create(part=part, order=4, question_type="matching", prompt="Match",
                                               correct_answer="C")
        for label in "ABC":
            Option.objects.create(question=self.q_match, label=label, text=f"Heading {label}")

    def test_full_flow_server_side_scoring(self):
        api = self.api(self.student)
        r = api.post(f"/api/exams/reading/{self.exam.pk}/start/")
        self.assertEqual(r.status_code, 201, r.content)
        attempt_id = r.json()["id"]
        # The exam payload never contains correct answers
        detail = api.get(f"/api/exams/{self.exam.pk}/").json()
        self.assertNotIn("correct_answer", str(detail))
        self.assertNotIn("is_correct", str(detail))
        # Autosave then submit (client-sent "score" is ignored)
        r = api.patch(f"/api/attempts/{attempt_id}/answers/", {"answers": {str(self.q_mcq.pk): self.opt_ok.pk}},
                      format="json")
        self.assertEqual(r.json()["saved"], 1)
        r = api.post(f"/api/attempts/{attempt_id}/submit/", {"score": 999, "answers": {
            str(self.q_tf.pk): "not given", str(self.q_gap.pk): "The Library", str(self.q_match.pk): "B"}},
            format="json")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["correct_count"], 3)
        self.assertEqual(data["incorrect_count"], 1)
        self.assertEqual(Decimal(data["score"]), Decimal("3"))
        self.assertEqual(Decimal(data["percentage"]), Decimal("75.00"))
        self.assertEqual(Decimal(data["result"]["scaled_score"]), Decimal("56"))  # 75% of 75
        self.assertEqual(data["result"]["cefr_level"], "B2")
        # Cannot resubmit
        self.assertEqual(api.post(f"/api/attempts/{attempt_id}/submit/", {}, format="json").status_code, 400)
        # Other students cannot see it
        self.assertEqual(self.api(self.other).get(f"/api/attempts/{attempt_id}/").status_code, 404)
        self.assertEqual(self.web(self.other).get(reverse("results:detail", args=[attempt_id])).status_code, 403)
        # Owner and admin can view the result page
        self.assertEqual(self.web(self.student).get(reverse("results:detail", args=[attempt_id])).status_code, 200)
        self.assertEqual(self.web(self.admin).get(reverse("results:detail", args=[attempt_id])).status_code, 200)

    def test_scores_are_read_only(self):
        attempt = ExamAttempt.objects.create(student=self.student, exam=self.exam)
        api = self.api(self.student)
        self.assertEqual(api.patch(f"/api/attempts/{attempt.pk}/", {"score": 9}, format="json").status_code, 405)
        self.assertEqual(api.post("/api/results/", {"score": 9}, format="json").status_code, 405)

    def test_admin_cannot_take_exam(self):
        r = self.api(self.admin).post(f"/api/exams/{self.exam.pk}/start/")
        self.assertEqual(r.status_code, 403)

    def test_multilevel_scaled_score(self):
        api = self.api(self.student)
        attempt_id = api.post(f"/api/exams/{self.exam.pk}/start/").json()["id"]
        r = api.post(f"/api/attempts/{attempt_id}/submit/", {"answers": {str(self.q_mcq.pk): self.opt_ok.pk}},
                     format="json").json()
        self.assertEqual(Decimal(r["result"]["scaled_score"]), Decimal("19"))  # 25% of 75 rounded
        self.assertEqual(r["result"]["cefr_level"], "Below B1")


class WritingTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.exam = MockExam.objects.create(title="Multilevel Writing #1", section="writing", time_limit=60,
                                            is_published=True)
        self.t1 = WritingTask.objects.create(exam=self.exam, order=1, title="Task 1.1", task_type="task1_1",
                                             topic="Write to a friend", minimum_word_count=50)
        self.t2 = WritingTask.objects.create(exam=self.exam, order=2, title="Task 2", task_type="task2",
                                             topic="Discuss both views", minimum_word_count=250)

    def test_writing_flow_with_ai(self):
        fake = FakeLLM(score=50)
        with mock.patch("ai.services.get_llm_provider", return_value=fake):
            api = self.api(self.student)
            attempt_id = api.post(f"/api/exams/writing/{self.exam.pk}/start/").json()["id"]
            with self.captureOnCommitCallbacks(execute=True):
                r = api.post(f"/api/attempts/{attempt_id}/submit/", {"essays": {
                    str(self.t1.pk): "The chart shows data. " * 30, str(self.t2.pk): "Some people think. " * 60}},
                    format="json")
            self.assertEqual(r.status_code, 200, r.content)
        attempt = ExamAttempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, "completed")
        subs = WritingSubmission.objects.filter(attempt=attempt)
        self.assertEqual(subs.count(), 2)
        for s in subs:
            self.assertEqual(s.status, "completed")
            self.assertEqual(s.evaluation.provider, "fake")
            # overall recomputed server-side from criteria: mean(50, 50, 51, 49) = 50
            self.assertEqual(s.evaluation.overall_score, Decimal("50"))
            self.assertEqual(s.evaluation.grammar_mistakes[0]["correction"], "He goes")
        self.assertEqual(attempt.result.scaled_score, Decimal("50"))
        self.assertEqual(attempt.result.cefr_level, "B1")
        self.assertEqual(len(fake.calls), 2)
        # Pages
        sub = subs.first()
        self.assertEqual(self.web(self.student).get(reverse("dashboard:writing_detail", args=[sub.pk])).status_code, 200)
        self.assertEqual(self.web(self.other).get(reverse("dashboard:writing_detail", args=[sub.pk])).status_code, 403)
        self.assertEqual(self.web(self.admin).get(reverse("admin_dashboard:writing_detail", args=[sub.pk])).status_code,
                         200)

    def test_missing_api_key_fails_honestly(self):
        with self.settings(AI_PROVIDER="anthropic", AI_API_KEY=""):
            api = self.api(self.student)
            attempt_id = api.post(f"/api/exams/{self.exam.pk}/start/").json()["id"]
            with self.captureOnCommitCallbacks(execute=True):
                api.post(f"/api/attempts/{attempt_id}/submit/", {"essays": {str(self.t2.pk): "An essay text here."}},
                         format="json")
        attempt = ExamAttempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, "failed")
        failed = WritingSubmission.objects.get(attempt=attempt, task=self.t2)
        self.assertEqual(failed.status, "failed")
        self.assertIn("AI_API_KEY", failed.error_message)
        self.assertFalse(hasattr(failed, "evaluation") and failed.evaluation)


class SpeakingTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.exam = MockExam.objects.create(title="Speaking #1", section="speaking",
                                            time_limit=15, is_published=True)
        self.q1 = SpeakingQuestion.objects.create(exam=self.exam, part=1, order=1, question="Do you work or study?")
        self.q2 = SpeakingQuestion.objects.create(exam=self.exam, part=2, order=1, question="Describe a trip",
                                                  cue_card_points="where\nwhen", preparation_time=60,
                                                  speaking_time=120)

    def audio(self):
        return SimpleUploadedFile("answer.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 4000, content_type="audio/webm")

    def test_speaking_flow_and_recording_privacy(self):
        with mock.patch("ai.services.get_llm_provider", return_value=FakeLLM(55)), \
             mock.patch("ai.services.get_stt_provider", return_value=FakeSTT()):
            api = self.api(self.student)
            attempt_id = api.post(f"/api/exams/{self.exam.pk}/start/").json()["id"]
            for q in (self.q1, self.q2):
                with self.captureOnCommitCallbacks(execute=True):
                        r = api.post("/api/speaking/submissions/", {"attempt": attempt_id, "question": q.pk,
                                                                "audio_file": self.audio(), "duration": 25},
                                 format="multipart")
                self.assertEqual(r.status_code, 201, r.content)
            # duplicate answer rejected
            r = api.post("/api/speaking/submissions/", {"attempt": attempt_id, "question": self.q1.pk,
                                                        "audio_file": self.audio()}, format="multipart")
            self.assertEqual(r.status_code, 400)
            with self.captureOnCommitCallbacks(execute=True):
                r = api.post(f"/api/attempts/{attempt_id}/submit/", {}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        attempt = ExamAttempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.result.scaled_score, Decimal("55"))
        self.assertEqual(attempt.result.cefr_level, "B2")
        sub = SpeakingSubmission.objects.filter(attempt=attempt).first()
        self.assertIn("weekends", sub.transcript)
        self.assertFalse(sub.evaluation.pronunciation_assessed)
        self.assertIsNone(sub.evaluation.pronunciation_score)
        self.assertIn("not assessed", sub.evaluation.pronunciation_feedback.lower())
        url = reverse("speaking:audio", args=[sub.pk])
        self.assertEqual(self.web(self.student).get(url).status_code, 200)
        self.assertEqual(self.web(self.admin).get(url).status_code, 200)
        self.assertEqual(self.web(self.other).get(url).status_code, 403)
        r = self.web(self.student).get(url, HTTP_RANGE="bytes=0-99")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"].split("/")[0], "bytes 0-99")
        self.assertEqual(self.api(self.other).get(f"/api/speaking/submissions/{sub.pk}/audio/").status_code, 404)

    def test_rejects_disguised_file(self):
        api = self.api(self.student)
        attempt_id = api.post(f"/api/exams/{self.exam.pk}/start/").json()["id"]
        bad = SimpleUploadedFile("answer.webm", b"<?php echo 1; ?>" * 100, content_type="audio/webm")
        r = api.post("/api/speaking/submissions/", {"attempt": attempt_id, "question": self.q1.pk, "audio_file": bad},
                     format="multipart")
        self.assertEqual(r.status_code, 400)
        exe = SimpleUploadedFile("answer.exe", b"MZ" * 100)
        r = api.post("/api/speaking/submissions/", {"attempt": attempt_id, "question": self.q1.pk, "audio_file": exe},
                     format="multipart")
        self.assertEqual(r.status_code, 400)


class AccessControlTests(BaseTest):
    def test_role_boundaries(self):
        self.assertEqual(self.web(self.student).get("/admin-dashboard/").status_code, 403)
        self.assertEqual(self.api(self.student).get("/api/admin/users/").status_code, 403)
        self.assertEqual(self.web(self.student).get("/teacher/").status_code, 404)
        self.assertEqual(self.api(self.student).get("/api/admin/results/").status_code, 403)
        self.assertEqual(self.api(self.admin).get("/api/admin/users/?role=student").json()["count"], 2)

    def test_users_cannot_change_own_role(self):
        r = self.api(self.student).patch("/api/users/me/", {"role": "admin", "phone_number": "+998901234567"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "student")
        self.assertEqual(self.student.phone_number, "+998901234567")

    def test_jwt_auth(self):
        c = APIClient()
        r = c.post("/api/auth/register/", {"email": "new@example.com", "password": PASSWORD, "first_name": "N",
                                           "last_name": "U"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = c.post("/api/auth/login/", {"email": "NEW@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
        self.assertEqual(c.get("/api/users/me/").json()["email"], "new@example.com")
        self.assertEqual(c.post("/api/auth/logout/", {"refresh": r.json()["refresh"]}, format="json").status_code, 205)


class PageRenderTests(BaseTest):
    """Every main page renders for the role that may use it."""

    def setUp(self):
        super().setUp()
        self.mocks = {s: MockExam.objects.create(title=f"{s} mock", section=s, is_published=True)
                      for s in ("reading", "listening", "writing", "speaking")}
        part = ExamPart.objects.create(exam=self.mocks["reading"], title="P1", passage="text")
        Question.objects.create(part=part, prompt="q", question_type="gap_filling", correct_answer="a")
        WritingTask.objects.create(exam=self.mocks["writing"], title="T", task_type="task2", topic="t")
        SpeakingQuestion.objects.create(exam=self.mocks["speaking"], question="q")

    def assertPages(self, user, urls):
        c = self.web(user) if user else self.client
        for url in urls:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, f"{url} -> {r.status_code}")

    def test_public_pages(self):
        self.assertPages(None, ["/", "/exams/", "/exams/reading/", "/exams/full/",
                                "/accounts/login/", "/accounts/register/", "/accounts/password/reset/",
                                f"/exams/{self.mocks['reading'].pk}/"])

    def test_student_pages(self):
        urls = ["/dashboard/", "/dashboard/results/", "/dashboard/writing/", "/dashboard/speaking/",
                "/accounts/profile/"]
        self.assertPages(self.student, urls)
        c = self.web(self.student)
        for exam in self.mocks.values():
            r = c.post(reverse("exams:start", args=[exam.pk]))
            self.assertEqual(r.status_code, 302)
            self.assertEqual(c.get(r["Location"]).status_code, 200, exam.section)

    def test_admin_pages(self):
        urls = ["/admin-dashboard/", "/admin-dashboard/users/", f"/admin-dashboard/users/{self.student.pk}/",
                "/admin-dashboard/users/new/", "/admin-dashboard/full-mocks/", "/admin-dashboard/writing/",
                "/admin-dashboard/speaking/", "/admin-dashboard/results/?section=reading&min_score=10",
                "/admin-dashboard/settings/"]
        for s, exam in self.mocks.items():
            urls += [f"/admin-dashboard/mocks/section/{s}/", f"/admin-dashboard/mocks/section/{s}/new/",
                     f"/admin-dashboard/mocks/{exam.pk}/", f"/admin-dashboard/mocks/{exam.pk}/edit/"]
        part = self.mocks["reading"].parts.first()
        urls += [f"/admin-dashboard/parts/{part.pk}/questions/new/",
                 f"/admin-dashboard/mocks/{self.mocks['writing'].pk}/tasks/new/",
                 f"/admin-dashboard/mocks/{self.mocks['speaking'].pk}/speaking-questions/new/?part=2"]
        self.assertPages(self.admin, urls)

    def test_admin_creates_and_publishes_mock(self):
        c = self.web(self.admin)
        r = c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "New", "level": "",
                                                                   "time_limit": 60})
        exam = MockExam.objects.get(title="New")
        self.assertRedirects(r, f"/admin-dashboard/mocks/{exam.pk}/")
        c.post(f"/admin-dashboard/mocks/{exam.pk}/parts/new/", {"title": "P1", "order": 1, "passage": "Body"})
        part = exam.parts.get()
        r = c.post(f"/admin-dashboard/parts/{part.pk}/questions/new/", {
            "order": 1, "question_type": "multiple_choice", "prompt": "Q?", "correct_answer": "", "points": "1",
            "explanation": "", "opt-TOTAL_FORMS": "2", "opt-INITIAL_FORMS": "0", "opt-MIN_NUM_FORMS": "0",
            "opt-MAX_NUM_FORMS": "20", "opt-0-label": "A", "opt-0-text": "yes", "opt-0-is_correct": "on",
            "opt-0-order": "0", "opt-1-label": "B", "opt-1-text": "no", "opt-1-order": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Question.objects.get(exam=exam).options.count(), 2)
        c.post(f"/admin-dashboard/mocks/{exam.pk}/publish/")
        exam.refresh_from_db()
        self.assertTrue(exam.is_published)
        r = c.post(f"/admin-dashboard/mocks/{exam.pk}/duplicate/")
        copy = MockExam.objects.exclude(pk=exam.pk).get(title__startswith="New")
        self.assertFalse(copy.is_published)
        self.assertEqual(Question.objects.filter(exam=copy).count(), 1)


class DashboardInsightTests(BaseTest):
    def test_dashboard_widgets_use_real_data(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import Word
        from dashboard import insights
        from results.models import Result

        exam = MockExam.objects.create(title="R", section="reading", is_published=True)
        now = timezone.now()
        for days_ago, pct, scaled in [(2, Decimal("40"), Decimal("30")), (1, Decimal("60"), Decimal("45")),
                                      (0, Decimal("80"), Decimal("60"))]:
            a = ExamAttempt.objects.create(student=self.student, exam=exam, status="completed", percentage=pct)
            ExamAttempt.objects.filter(pk=a.pk).update(started_at=now - timedelta(days=days_ago),
                                                        completed_at=now - timedelta(days=days_ago))
            Result.objects.create(attempt=a, scaled_score=scaled, cefr_level=scoring.multilevel_to_cefr(scaled))
        act = insights.activity(self.student)
        self.assertEqual(act["streak"], 3)
        self.assertEqual(act["active_days"], 3)
        self.assertEqual(act["day"] + act["night"], 3)
        curve = insights.learning_curve(self.student)
        self.assertEqual((curve["latest"], curve["change"], curve["level"]), (60, 30, "B2"))
        reading = next(s for s in insights.skill_levels(self.student) if s["key"] == "reading")
        self.assertEqual((reading["count"], reading["score"], reading["level"]), (3, 60, "B2"))
        self.assertEqual(insights.results_overview(self.student)["best"], 60)
        self.assertEqual(insights.platform_stats()["attempts_all_time"], 3)
        self.assertEqual(len(insights.progression(self.student, "reading")), 3)
        self.assertEqual(insights.progression(self.student, "writing"), [])
        Word.objects.create(word="precarious", definition="likely to collapse")
        c = self.web(self.student)
        home = c.get("/dashboard/").content.decode()
        self.assertIn("precarious", home)
        self.assertIn("app-sidebar", home)
        self.assertEqual(c.get("/dashboard/results/?section=reading").status_code, 200)
        # Exam rooms render without the sidebar
        r = c.post(reverse("exams:start", args=[exam.pk]))
        self.assertNotIn("app-sidebar", c.get(r["Location"]).content.decode())
        # Other roles keep their own layouts
        self.assertNotIn("app-sidebar", self.web(self.admin).get("/exams/").content.decode())
        # removed from the student UI
        self.assertNotIn(">Learn</a>", home)
        self.assertNotIn('<h3 class="mb-0">Learn</h3>', home)
        self.assertNotIn("My courses", home)
        for removed in ["/courses/", "/quizzes/1/", "/teacher/", "/dashboard/certificates/", "/api/courses/",
                        "/admin-dashboard/teachers/", "/admin-dashboard/courses/"]:
            self.assertEqual(self.web(self.admin if "admin" in removed else self.student).get(removed).status_code,
                             404, removed)
        self.assertNotIn("All levels", c.get("/exams/").content.decode())


class FullMockTests(BaseTest):
    def setUp(self):
        super().setUp()
        from exams.models import FullMock

        def objective(section):
            exam = MockExam.objects.create(title=f"{section} 1", section=section, is_published=True)
            part = ExamPart.objects.create(exam=exam, title="P1", passage="text")
            q = Question.objects.create(part=part, prompt="q", question_type="gap_filling", correct_answer="yes")
            return exam, q

        self.listening, self.lq = objective("listening")
        self.reading, self.rq = objective("reading")
        self.writing = MockExam.objects.create(title="W", section="writing", is_published=True)
        self.task = WritingTask.objects.create(exam=self.writing, title="Task 2", task_type="task2", topic="t")
        self.speaking = MockExam.objects.create(title="S", section="speaking", is_published=True)
        self.sq = SpeakingQuestion.objects.create(exam=self.speaking, question="q")
        self.fm = FullMock.objects.create(title="Full #1", listening=self.listening, reading=self.reading,
                                          writing=self.writing, speaking=self.speaking, is_published=True)

    def test_full_mock_flow(self):
        from results.models import FullMockAttempt

        c = self.web(self.student)
        api = self.api(self.student)
        r = c.post(reverse("exams:full_start", args=[self.fm.pk]))
        full = FullMockAttempt.objects.get(student=self.student)
        self.assertRedirects(r, reverse("exams:full_progress", args=[full.pk]))
        self.assertContains(c.get(r["Location"]), "Start listening")

        def next_attempt(expected_section):
            resp = c.post(reverse("exams:full_progress", args=[full.pk]))
            attempt = ExamAttempt.objects.get(pk=resp["Location"].rstrip("/").split("/")[-1])
            self.assertEqual(attempt.exam.section, expected_section)
            self.assertEqual(attempt.full_mock_attempt_id, full.pk)
            # the exam room sends the student back to the full mock progress page
            self.assertContains(c.get(resp["Location"]), f"/exams/full/attempt/{full.pk}/")
            return attempt

        a = next_attempt("listening")
        api.post(f"/api/attempts/{a.pk}/submit/", {"answers": {str(self.lq.pk): "yes"}}, format="json")  # 75
        a = next_attempt("reading")
        api.post(f"/api/attempts/{a.pk}/submit/", {"answers": {str(self.rq.pk): "no"}}, format="json")  # 0
        with mock.patch("ai.services.get_llm_provider", return_value=FakeLLM(50)), \
             mock.patch("ai.services.get_stt_provider", return_value=FakeSTT()):
            a = next_attempt("writing")
            with self.captureOnCommitCallbacks(execute=True):
                api.post(f"/api/attempts/{a.pk}/submit/", {"essays": {str(self.task.pk): "My essay."}}, format="json")
            a = next_attempt("speaking")
            with self.captureOnCommitCallbacks(execute=True):
                api.post("/api/speaking/submissions/", {"attempt": a.pk, "question": self.sq.pk, "audio_file":
                         SimpleUploadedFile("a.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 4000)}, format="multipart")
            with self.captureOnCommitCallbacks(execute=True):
                api.post(f"/api/attempts/{a.pk}/submit/", {}, format="json")
        full.refresh_from_db()
        self.assertEqual(full.status, "completed")
        # mean(75, 0, 50, 50) = 43.75 -> 44
        self.assertEqual(full.score, Decimal("44"))
        self.assertEqual(full.cefr_level, "B1")
        # progress page now redirects to the result, which renders for owner/admin only
        self.assertRedirects(c.get(reverse("exams:full_progress", args=[full.pk])), full.get_absolute_url())
        self.assertContains(c.get(full.get_absolute_url()), "44")
        self.assertEqual(self.web(self.other).get(full.get_absolute_url()).status_code, 403)
        self.assertEqual(self.web(self.admin).get(full.get_absolute_url()).status_code, 200)
        self.assertEqual(self.web(self.student).get("/dashboard/results/?section=full").status_code, 200)
        self.assertEqual(api.get(f"/api/attempts/full/{full.pk}/").json()["score"], "44.0")
        # standalone attempts of the same exam are kept separate
        r = self.api(self.student).post(f"/api/exams/{self.reading.pk}/start/")
        self.assertIsNone(ExamAttempt.objects.get(pk=r.json()["id"]).full_mock_attempt_id)

    def test_admin_pages_and_guards(self):
        c = self.web(self.admin)
        for url in ["/admin-dashboard/full-mocks/", "/admin-dashboard/full-mocks/new/",
                    f"/admin-dashboard/full-mocks/{self.fm.pk}/", f"/admin-dashboard/full-mocks/{self.fm.pk}/edit/",
                    "/exams/", "/exams/full/", f"/exams/full/{self.fm.pk}/"]:
            self.assertEqual(c.get(url).status_code, 200, url)
        # a section mock that belongs to a full mock cannot be deleted
        c.post(f"/admin-dashboard/mocks/{self.reading.pk}/delete/")
        self.assertTrue(MockExam.objects.filter(pk=self.reading.pk).exists())
        # publishing requires published sections
        self.reading.is_published = False
        self.reading.save()
        self.fm.is_published = False
        self.fm.save()
        c.post(f"/admin-dashboard/full-mocks/{self.fm.pk}/publish/")
        self.fm.refresh_from_db()
        self.assertFalse(self.fm.is_published)
        self.assertEqual(self.web(self.student).get("/dashboard/").status_code, 200)


class SeedContentTests(BaseTest):
    def test_seed_cefr_creates_two_valid_mocks_per_section(self):
        from django.core.management import call_command

        from exams.models import FullMock
        from exams.services import validate_publishable

        with mock.patch("core.management.commands.seed_cefr.tts_available", return_value=False):
            call_command("seed_cefr", stdout=open("/dev/null", "w"))
        for section in ("reading", "listening", "writing", "speaking"):
            exams = MockExam.objects.filter(section=section, title__startswith="Multilevel ")
            self.assertEqual(exams.count(), 2, section)
            for exam in exams:
                problems = validate_publishable(exam)
                if section == "listening":  # no TTS in this test -> only the audio is missing
                    self.assertEqual(problems, ["Upload the listening audio."])
                else:
                    self.assertEqual(problems, [], exam.title)
        speaking = MockExam.objects.filter(section="speaking").first()
        self.assertEqual(sorted(set(speaking.speaking_questions.values_list("part", flat=True))), [1, 2, 3, 4])
        self.assertEqual(speaking.speaking_questions.count(), 8)
        argument = speaking.speaking_questions.get(part=4)
        self.assertEqual(len(argument.arguments["for"]), 2)
        self.assertEqual(FullMock.objects.count(), 2)
        # running it again does not duplicate anything
        with mock.patch("core.management.commands.seed_cefr.tts_available", return_value=False):
            call_command("seed_cefr", stdout=open("/dev/null", "w"))
        self.assertEqual(MockExam.objects.filter(title__startswith="Multilevel ").count(), 8)


class PartPracticeTests(BaseTest):
    def setUp(self):
        super().setUp()
        from django.core.management import call_command

        with mock.patch("core.management.commands.seed_cefr.tts_available", return_value=False):
            call_command("seed_cefr", stdout=open("/dev/null", "w"))
        self.reading = MockExam.objects.get(title="Multilevel Reading — Mock 01")
        self.writing = MockExam.objects.get(title="Multilevel Writing — Mock 01")
        self.speaking = MockExam.objects.get(title="Multilevel Speaking — Mock 01")

    def test_reading_part_practice_grades_only_that_part(self):
        from results.services import practice_options

        api = self.api(self.student)
        options = api.get(f"/api/exams/{self.reading.pk}/practice-options/").json()
        self.assertEqual(len(options), 3)
        part3 = options[2]
        r = api.post(f"/api/exams/{self.reading.pk}/start/", {"practice": part3["key"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        attempt = ExamAttempt.objects.get(pk=r.json()["id"])
        self.assertEqual(attempt.practice_label, "Part 3 · True / False / No Information")
        self.assertEqual(attempt.time_limit, part3["minutes"])
        part = self.reading.parts.get(order=3)
        answers = {str(q.pk): q.correct_answer for q in part.questions.all()}
        other = self.reading.parts.get(order=1).questions.first()
        answers[str(other.pk)] = other.correct_answer.split("|")[0]  # outside the practised part: ignored
        data = api.post(f"/api/attempts/{attempt.pk}/submit/", {"answers": answers}, format="json").json()
        self.assertEqual((data["correct_count"], data["incorrect_count"], data["unanswered_count"]), (5, 0, 0))
        # one part is not a whole test: no 0–75 score or CEFR level, and it doesn't set the best score
        self.assertIsNone(data["result"]["scaled_score"])
        self.assertEqual(data["result"]["cefr_level"], "")
        self.assertEqual(ExamAttempt.objects.get(pk=attempt.pk).display_score, "5/5 correct")
        page = self.web(self.student).get(f"/results/{attempt.pk}/").content.decode()
        self.assertIn("Part practice", page)
        self.assertNotIn("OF 75", page)
        from dashboard.services import student_stats
        self.assertIsNone(student_stats(self.student)["best_multilevel"])
        self.assertEqual(practice_options(self.reading)[0]["sub"], "5 questions")
        # unknown practice keys are rejected
        bad = api.post(f"/api/exams/{self.reading.pk}/start/", {"practice": "part:999999"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.web(self.student).get(f"/exams/{self.reading.pk}/practice/").status_code, 200)

    def test_writing_and_speaking_practice(self):
        task = self.writing.writing_tasks.get(task_type="task1_1")
        c = self.web(self.student)
        r = c.post(reverse("exams:start", args=[self.writing.pk]), {"practice": f"task:{task.pk}"})
        attempt = ExamAttempt.objects.get(pk=r["Location"].rstrip("/").split("/")[-1])
        page = c.get(r["Location"]).content.decode()
        self.assertIn("Task 1.1", page)
        self.assertNotIn("Task 1.2 —", page)
        with mock.patch("ai.services.get_llm_provider", return_value=FakeLLM(40)):
            with self.captureOnCommitCallbacks(execute=True):
                self.api(self.student).post(f"/api/attempts/{attempt.pk}/submit/",
                                            {"essays": {str(task.pk): "Hi Sam, the club is moving."}}, format="json")
        attempt.refresh_from_db()
        self.assertEqual(attempt.writing_submissions.count(), 1)
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.result.scaled_score, Decimal("40"))

        api = self.api(self.student)
        r = api.post(f"/api/exams/{self.speaking.pk}/start/", {"practice": "part:4"}, format="json")
        sp = ExamAttempt.objects.get(pk=r.json()["id"])
        part1 = self.speaking.speaking_questions.filter(part=1).first()
        audio = SimpleUploadedFile("a.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 4000)
        r = api.post("/api/speaking/submissions/", {"attempt": sp.pk, "question": part1.pk, "audio_file": audio},
                     format="multipart")
        self.assertEqual(r.status_code, 400)  # question outside the practised part
        self.assertContains(self.web(self.student).get(reverse("exams:take", args=[sp.pk])), "Part 3")

    def test_mock_cards(self):
        c = self.web(self.student)
        page = c.get("/exams/speaking/").content.decode()
        self.assertIn("#01", page)
        self.assertIn("4/4 READY", page)
        self.assertIn("PART 1.2", page)
        self.assertIn("Train vs plane travel", page)
        writing = c.get("/exams/writing/").content.decode()
        self.assertIn("3/3 READY", writing)
        self.assertIn("Cooking club changes", writing)
        listening = c.get("/exams/listening/").content.decode()
        self.assertIn("No listening mocks yet", listening)  # seeded without audio in tests -> stays unpublished
        self.assertNotIn("PDF", page)
        self.assertNotIn("data-copy", page)

    def test_continue_banner_and_discard(self):
        api = self.api(self.student)
        a1 = api.post(f"/api/exams/{self.reading.pk}/start/").json()["id"]
        qs = list(self.reading.parts.get(order=1).questions.all()[:2])
        api.patch(f"/api/attempts/{a1}/answers/", {"answers": {str(q.pk): "word" for q in qs}}, format="json")
        api.post(f"/api/exams/{self.writing.pk}/start/")
        c = self.web(self.student)
        hub = c.get("/exams/").content.decode()
        self.assertIn("Continue where you left off", hub)
        self.assertIn("2 unfinished", hub)
        self.assertIn("Also unfinished", hub)
        self.assertIn("CEFR →", hub)
        for removed in ("IELTS", "Plus"):
            self.assertNotIn(removed, hub)
        reading_item = self.reading.title
        self.assertIn(reading_item, hub)
        self.assertIn("Continue where you left off", c.get("/dashboard/").content.decode())
        c.post(reverse("exams:discard", args=[a1]), {"next": "/exams/"})
        self.assertEqual(ExamAttempt.objects.get(pk=a1).status, "discarded")
        self.assertIn("was discarded", c.get("/exams/").content.decode())  # flash message, shown once
        self.assertNotIn(reading_item, c.get("/exams/").content.decode())
        self.assertNotIn(self.reading.title, c.get("/dashboard/results/").content.decode())
        # another student's attempt cannot be discarded
        other = self.api(self.other).post(f"/api/exams/{self.writing.pk}/start/").json()["id"]
        self.assertEqual(c.post(reverse("exams:discard", args=[other])).status_code, 404)

    def test_exam_room_layout_and_drafts(self):
        c = self.web(self.student)
        r = c.post(reverse("exams:start", args=[self.reading.pk]))
        page = c.get(r["Location"]).content.decode()
        self.assertIn('class="gap"', page)            # Part 1 gaps are inline in the passage
        self.assertNotIn("(1) ______", page)
        self.assertIn("data-slot-for", page)          # Part 2 matching uses drag & drop slots
        self.assertIn("Questions 10–14: True / False / No Information", page)
        self.assertIn("Leave the test?", page)  # exit dialog
        self.assertIn("№01", page)
        self.assertNotIn("harvesting", page)          # never leak answers
        # writing drafts autosave server-side and come back on resume
        api = self.api(self.student)
        attempt = api.post(f"/api/exams/{self.writing.pk}/start/").json()["id"]
        task = self.writing.writing_tasks.first()
        r = api.patch(f"/api/attempts/{attempt}/drafts/", {"drafts": {str(task.pk): "Hi Sam, guess what"}},
                      format="json")
        self.assertEqual(r.json()["saved"], 1)
        self.assertIn("Hi Sam, guess what", c.get(reverse("exams:take", args=[attempt])).content.decode())
        self.assertIn("tasks drafted · 4 words", c.get("/exams/").content.decode())
        self.assertEqual(self.api(self.other).patch(f"/api/attempts/{attempt}/drafts/", {"drafts": {}},
                                                    format="json").status_code, 404)

    def test_map_labelling_grading(self):
        from exams.models import ExamPart, Question

        exam = MockExam.objects.create(title="Map", section="listening", is_published=True)
        part = ExamPart.objects.create(exam=exam, title="Map", order=1)
        q = Question.objects.create(part=part, order=1, question_type="map_labelling", prompt="Bus stop",
                                    correct_answer="E")
        for letter in "ABCDE":
            Option.objects.create(question=q, label=letter, text="")
        api = self.api(self.student)
        attempt = api.post(f"/api/exams/{exam.pk}/start/").json()["id"]
        data = api.post(f"/api/attempts/{attempt}/submit/", {"answers": {str(q.pk): "e"}}, format="json").json()
        self.assertEqual(data["correct_count"], 1)


class CefrAdminTests(BaseTest):
    def test_admin_builds_reading_mock_with_cefr_parts(self):
        from exams.models import ExamPart, Question

        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "Reading 07", "level": "", "time_limit": 60,
                                                               "cefr_layout": "on"})
        exam = MockExam.objects.get(title="Reading 07")
        self.assertEqual(list(exam.parts.values_list("cefr_part", flat=True)), ["R1", "R2", "R3", "R4", "R5"])
        manage = c.get(f"/admin-dashboard/mocks/{exam.pk}/").content.decode()
        self.assertIn("CEFR structure", manage)
        self.assertNotIn("Yes / No", manage)
        part1 = exam.parts.get(cefr_part="R1")
        form = c.get(f"/admin-dashboard/parts/{part1.pk}/questions/new/").content.decode()
        self.assertIn('value="gap_filling"', form)
        self.assertNotIn('value="true_false_not_given"', form)   # not allowed in Part 1
        r = c.post(f"/admin-dashboard/parts/{part1.pk}/questions/new/", {
            "order": 1, "question_type": "true_false_not_given", "prompt": "x", "correct_answer": "TRUE",
            "points": "1", "explanation": "", "opt-TOTAL_FORMS": "0", "opt-INITIAL_FORMS": "0",
            "opt-MIN_NUM_FORMS": "0", "opt-MAX_NUM_FORMS": "20"})
        self.assertEqual(r.status_code, 200)  # rejected, form shown again
        r = c.post(f"/admin-dashboard/parts/{part1.pk}/questions/new/", {
            "order": 1, "question_type": "gap_filling", "prompt": "Gap 1", "correct_answer": "river|rivers",
            "points": "1", "explanation": "", "opt-TOTAL_FORMS": "0", "opt-INITIAL_FORMS": "0",
            "opt-MIN_NUM_FORMS": "0", "opt-MAX_NUM_FORMS": "20"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Question.objects.get(exam=exam).question_type, "gap_filling")
        listening = c.post("/admin-dashboard/mocks/section/listening/new/", {"title": "Listening 07", "level": "",
                                                                             "time_limit": 40, "cefr_layout": "on"})
        self.assertEqual(ExamPart.objects.filter(exam__title="Listening 07").count(), 6)


class GeminiProviderTests(TestCase):
    """The Gemini provider talks REST via httpx2; the network is mocked here."""

    def setUp(self):
        patcher = mock.patch("ai.providers.gemini_provider.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_retries_busy_server_then_succeeds(self):
        from ai.providers.gemini_provider import GeminiProvider
        ok = {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]}
        busy = self._response({"error": {"message": "high demand"}}, status=503)
        with mock.patch("httpx2.post", side_effect=[busy, busy, self._response(ok)]) as post:
            data = GeminiProvider(api_key="k").generate_json(system="s", prompt="p", schema={}, schema_name="x")
        self.assertEqual(data, {"a": 1})
        self.assertEqual(post.call_count, 3)
        bad_key = self._response({"error": {"message": "API key not valid."}}, status=400)
        with mock.patch("httpx2.post", return_value=bad_key) as post:
            with self.assertRaises(Exception):
                GeminiProvider(api_key="k").generate_json(system="s", prompt="p", schema={}, schema_name="x")
        self.assertEqual(post.call_count, 1)  # configuration errors are not retried

    def _response(self, payload, status=200):
        resp = mock.MagicMock(status_code=status)
        resp.json.return_value = payload
        return resp

    def test_generate_json_sends_schema_and_parses_answer(self):
        from ai.providers.gemini_provider import GeminiProvider
        answer = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"ok": true}'}]}}]}
        with mock.patch("httpx2.post", return_value=self._response(answer)) as post:
            data = GeminiProvider(api_key="k").generate_json(system="sys", prompt="p", schema={"type": "object"},
                                                             schema_name="x")
        self.assertEqual(data, {"ok": True})
        self.assertIn("gemini-3.5-flash:generateContent", post.call_args[0][0])
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "k")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["generationConfig"]["responseJsonSchema"], {"type": "object"})
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "sys")

    def test_transcribe_sends_inline_audio(self):
        from ai.providers.gemini_provider import GeminiSTTProvider
        answer = {"candidates": [{"content": {"parts": [{"text": " I like reading books. "}]}}]}
        with mock.patch("httpx2.post", return_value=self._response(answer)) as post:
            text = GeminiSTTProvider(api_key="k").transcribe(data=b"abc", filename="a.webm",
                                                             content_type="audio/webm;codecs=opus")
        self.assertEqual(text, "I like reading books.")
        part = post.call_args.kwargs["json"]["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(part["mime_type"], "audio/webm")

    def test_errors_are_translated(self):
        import httpx2
        from ai.exceptions import AIConfigurationError, AIProviderError
        from ai.providers.gemini_provider import GeminiProvider

        def error(code, message):
            return self._response({"error": {"message": message}}, status=code)

        provider = GeminiProvider(api_key="k")
        call = dict(system="s", prompt="p", schema={}, schema_name="x")
        with mock.patch("httpx2.post", return_value=error(400, "API key not valid.")):
            with self.assertRaises(AIConfigurationError):
                provider.generate_json(**call)
        for code in (429, 503):
            with mock.patch("httpx2.post", return_value=error(code, "high demand")):
                with self.assertRaises(AIProviderError) as ctx:
                    provider.generate_json(**call)
                self.assertTrue(ctx.exception.retryable)
        with mock.patch("httpx2.post", side_effect=httpx2.ReadTimeout("slow")):
            with self.assertRaises(AIProviderError) as ctx:
                provider.generate_json(**call)
            self.assertTrue(ctx.exception.retryable)
        cut = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
        with mock.patch("httpx2.post", return_value=self._response(cut)):
            with self.assertRaises(AIProviderError):
                provider.generate_json(**call)
        with self.assertRaises(AIConfigurationError):
            GeminiProvider(api_key="").generate_json(**call)

    @override_settings(AI_PROVIDER="gemini", STT_PROVIDER="gemini", AI_API_KEY="k", STT_API_KEY="k",
                       AI_MODEL="", STT_MODEL="")
    def test_service_picks_gemini(self):
        from ai.services import AIService, get_llm_provider, get_stt_provider
        self.assertEqual(get_llm_provider().name, "gemini")
        self.assertEqual(get_stt_provider().name, "gemini")
        status = AIService.status()
        self.assertEqual(status["model"], "gemini-3.5-flash")
        self.assertEqual(status["stt_model"], "gemini-3.5-flash")


class QuickEntryTests(BaseTest):
    """Admin pastes a whole part / speaking set / writing set as plain text."""

    def _mock(self, section):
        c = self.web(self.admin)
        c.post(f"/admin-dashboard/mocks/section/{section}/new/", {"title": f"Q {section}", "level": "B2",
                                                                    "time_limit": 60, "cefr_layout": "on"})
        return c, MockExam.objects.get(title=f"Q {section}")

    def test_parser_recognises_every_cefr_type(self):
        from admin_dashboard.quick import parse_part
        from exams.models import ExamPart

        part = ExamPart(cefr_part="", title="Custom")
        text = """1. ______ = library | libraries
2. = free
3. The library opened in 1998. = T
4. What is the writer's purpose?
A) to inform
*B) to persuade
C) to entertain

OPTIONS
A) Weekend Photography
B) Coding for Teens
5. Aziz wants to talk to clients. = b

OPTIONS
i) Why we forget
ii) A surprising
experiment
6. Paragraph A = ii
"""
        items, errors = parse_part(text, part)
        self.assertEqual(errors, [])
        by = {i.number: i for i in items}
        self.assertEqual((by[1].qtype, by[1].answer, by[1].prompt), ("gap_filling", "library|libraries", "Gap 1"))
        self.assertEqual(by[2].answer, "free")
        self.assertEqual((by[3].qtype, by[3].answer), ("true_false_not_given", "TRUE"))
        self.assertEqual(by[4].qtype, "multiple_choice")
        self.assertEqual([ok for _, _, ok in by[4].options], [False, True, False])
        self.assertEqual((by[5].qtype, by[5].answer, len(by[5].options)), ("matching", "B", 2))
        self.assertEqual((by[6].qtype, by[6].answer), ("headings", "ii"))
        self.assertEqual(by[6].options[1], ("ii", "A surprising experiment", False))

    def test_parser_reports_problems_in_plain_words(self):
        from admin_dashboard.quick import parse_part
        from exams.models import ExamPart

        _, errors = parse_part("1. ______\n2. Which?\nA) x\nB) y\nHello there", ExamPart(cefr_part="R1"))
        joined = " ".join(errors)
        self.assertIn("Question 1: write the answer", joined)
        self.assertIn("Question 2: mark exactly one correct option", joined)
        self.assertIn("Multiple choice is not used in Part 1", joined)

    def test_quick_part_saves_and_students_are_graded(self):
        c, exam = self._mock("reading")
        part1 = exam.parts.get(cefr_part="R1")
        url = f"/admin-dashboard/parts/{part1.pk}/quick/"
        body = {"passage": "THE LIBRARY\n\nThe (1) ______ is big and the (2) ______ is free.",
                "questions": "1. ______ = library\n2. ______ = entry | entrance"}
        preview = c.post(url, {**body, "action": "preview"}).content.decode()
        self.assertIn("2 questions ready", preview)
        self.assertEqual(part1.questions.count(), 0)  # preview saves nothing
        r = c.post(url, {**body, "action": "save"})
        self.assertEqual(r.status_code, 302)
        part1.refresh_from_db()
        self.assertIn("(1) ______", part1.passage)
        self.assertEqual(list(part1.questions.values_list("correct_answer", flat=True)), ["library", "entry|entrance"])
        # the page re-opens with the same text, so it can be edited again
        self.assertIn("2. entry | entrance", c.get(url).content.decode())

        exam.is_published = True
        exam.save()
        api = self.api(self.student)
        attempt = api.post(f"/api/exams/{exam.pk}/start/").json()["id"]
        q1, q2 = part1.questions.order_by("order")
        api.patch(f"/api/attempts/{attempt}/answers/", {"answers": {str(q1.pk): "Library", str(q2.pk): "entrance"}},
                  format="json")
        api.post(f"/api/attempts/{attempt}/submit/", {}, format="json")
        self.assertEqual(ExamAttempt.objects.get(pk=attempt).answers.filter(is_correct=True).count(), 2)
        # answered parts are locked: replacing would delete student answers
        r = c.post(url, {**body, "action": "save"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(part1.questions.count(), 2)

    def test_quick_speaking_and_writing(self):
        from exams.models import SpeakingQuestion

        c, sp = self._mock("speaking")
        text = """PART 1.1
Do you work or study?
What music do you like?
How do you travel?
PART 1.2
Compare the two pictures.
Which is better? Why?
Should cities have more parks?
PART 2
Describe a skill you want to learn.
- what it is
- why
PART 3
Everyone should volunteer.
for: it helps
Against: people are busy"""
        r = c.post(f"/admin-dashboard/mocks/{sp.pk}/quick-speaking/", {"text": text, "action": "save"})
        self.assertEqual(r.status_code, 302)
        qs = list(SpeakingQuestion.objects.filter(exam=sp).order_by("part", "order"))
        self.assertEqual([q.part for q in qs], [1, 1, 1, 2, 2, 2, 3, 4])
        self.assertEqual((qs[3].preparation_time, qs[4].preparation_time, qs[7].speaking_time), (10, 5, 120))
        self.assertEqual(qs[6].cue_points, ["what it is", "why"])
        self.assertEqual(qs[7].cue_card_points, "For: it helps\nAgainst: people are busy")

        c, wr = self._mock("writing")
        text = """SITUATION
Your gym is closing for repairs.
TASK 1.1
Write to a friend.
TASK 1.2
Write to the manager.
TASK 2
Discuss sport every day."""
        r = c.post(f"/admin-dashboard/mocks/{wr.pk}/quick-writing/", {"text": text, "action": "save"})
        self.assertEqual(r.status_code, 302)
        tasks = list(wr.writing_tasks.order_by("order"))
        self.assertEqual([(t.task_type, t.minimum_word_count, t.maximum_word_count) for t in tasks],
                         [("task1_1", 50, 70), ("task1_2", 120, 150), ("task2", 180, 200)])
        self.assertTrue(tasks[0].topic.startswith("Your gym is closing"))
        self.assertEqual(tasks[2].topic, "Discuss sport every day.")
        self.assertIn("SITUATION", c.get(f"/admin-dashboard/mocks/{wr.pk}/quick-writing/").content.decode())

    def test_manage_page_offers_quick_entry(self):
        c, exam = self._mock("listening")
        page = c.get(f"/admin-dashboard/mocks/{exam.pk}/").content.decode()
        self.assertIn("⚡ Quick entry", page)
        part4 = exam.parts.get(cefr_part="L4")
        quick = c.get(f"/admin-dashboard/parts/{part4.pk}/quick/").content.decode()
        self.assertIn("Map labelling", quick)
        self.assertIn('name="audio"', quick)
        r = c.post(f"/admin-dashboard/parts/{part4.pk}/quick/",
                   {"passage": "", "questions": "OPTIONS: A-F\n21. Swimming pool = d\n22. Car park = A",
                    "action": "save"})
        self.assertEqual(r.status_code, 302)
        q = part4.questions.get(order=21)
        self.assertEqual((q.question_type, q.correct_answer, q.options.count()), ("map_labelling", "D", 6))


class QuickEntryNaturalFormatTests(BaseTest):
    def test_answers_only_and_numbered_gaps_in_text(self):
        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "Plants", "time_limit": 60, "cefr_layout": "on"})
        part = MockExam.objects.get(title="Plants").parts.get(cefr_part="R1")
        r = c.post(f"/admin-dashboard/parts/{part.pk}/quick/", {
            "action": "save",
            "passage": "First, both 1. ______ and children are sensitive. A plant grows in an 2.______ of care.",
            "questions": "1. plants\n2. environment"})
        self.assertEqual(r.status_code, 302)
        part.refresh_from_db()
        self.assertIn("both (1) ______ and", part.passage)
        self.assertIn("an (2) ______ of care", part.passage)
        self.assertEqual(list(part.questions.values_list("correct_answer", flat=True)), ["plants", "environment"])
        preview = c.post(f"/admin-dashboard/parts/{part.pk}/quick/", {
            "action": "preview", "passage": "No gaps here.", "questions": "1. plants\n2. environment"}).content.decode()
        self.assertIn("not marked in the text", preview)


class CsrfFailureTests(BaseTest):
    def test_expired_form_shows_friendly_page(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        r = c.post("/admin-dashboard/", {"x": "1"}, HTTP_REFERER="http://testserver/admin-dashboard/parts/1/quick/")
        self.assertEqual(r.status_code, 403)
        page = r.content.decode()
        self.assertIn("This page expired", page)
        self.assertIn('href="http://testserver/admin-dashboard/parts/1/quick/"', page)
        r = c.post("/admin-dashboard/", {"x": "1"}, HTTP_REFERER="https://evil.example/")
        self.assertIn('href="/"', r.content.decode())  # never send people to another site


class NoInformationTests(TestCase):
    def test_old_and_new_spellings_are_the_same_choice(self):
        from exams.models import Question
        from exams.scoring import check_answer

        q = Question(question_type=Question.Type.TFNG, correct_answer="NO INFORMATION")
        for given in ("NO INFORMATION", "no information", "Not Given", "NG", "NI"):
            self.assertTrue(check_answer(q, given), given)
        self.assertFalse(check_answer(q, "FALSE"))
        self.assertEqual(Question(question_type=Question.Type.TFNG).fixed_choices, ["TRUE", "FALSE", "NO INFORMATION"])

    def test_quick_entry_accepts_short_forms(self):
        from admin_dashboard.quick import parse_part
        from exams.models import ExamPart

        items, errors = parse_part("1. A. = NI\n2. B. = NG\n3. C. = no information\n4. D. = F", ExamPart(cefr_part="R4"))
        self.assertEqual(errors, [])
        self.assertEqual([i.answer for i in items], ["NO INFORMATION"] * 3 + ["FALSE"])


class GuestTrialTests(BaseTest):
    """A visitor may take ONE mock without an account; registering or logging in keeps the result."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        from django.core.management import call_command

        cache.clear()
        with mock.patch("core.management.commands.seed_cefr.tts_available", return_value=False):
            call_command("seed_cefr", stdout=open("/dev/null", "w"))
        self.reading = MockExam.objects.get(title="Multilevel Reading — Mock 01")
        self.reading2 = MockExam.objects.get(title="Multilevel Reading — Mock 02")

    def _guest_take_one(self):
        from django.test import Client

        c = Client()
        detail = c.get(f"/exams/{self.reading.pk}/").content.decode()
        self.assertIn("Your first mock is free", detail)
        r = c.post(f"/exams/{self.reading.pk}/start/")
        attempt = ExamAttempt.objects.latest("pk")
        self.assertRedirects(r, f"/exams/attempt/{attempt.pk}/", fetch_redirect_response=False)
        self.assertTrue(attempt.student.is_guest)
        return c, attempt

    def test_second_mock_needs_an_account(self):
        c, attempt = self._guest_take_one()
        # resuming the same mock is fine
        r = c.post(f"/exams/{self.reading.pk}/start/")
        self.assertRedirects(r, f"/exams/attempt/{attempt.pk}/", fetch_redirect_response=False)
        # a second, different mock is not
        r = c.post(f"/exams/{self.reading2.pk}/start/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/accounts/register/?next="))
        self.assertEqual(ExamAttempt.objects.filter(student=attempt.student).count(), 1)
        # full mocks always need an account; the guest's page shows the register button
        self.assertIn("Create free account", c.get(f"/exams/{self.reading2.pk}/").content.decode())
        self.assertNotIn("guest.invalid", c.get(f"/results/{attempt.pk}/").content.decode())

    def test_registering_keeps_the_free_result(self):
        c, attempt = self._guest_take_one()
        guest_id = attempt.student_id
        page = c.get("/accounts/register/").content.decode()
        self.assertIn("will be saved to this account", page)
        r = c.post("/accounts/register/", {"first_name": "Ali", "last_name": "Valiyev", "email": "ali@example.com",
                                           "password1": "Very-long-pass-2026", "password2": "Very-long-pass-2026",
                                           "next": f"/exams/{self.reading2.pk}/"})
        self.assertRedirects(r, f"/exams/{self.reading2.pk}/", fetch_redirect_response=False)
        user = User.objects.get(email="ali@example.com")
        self.assertEqual(user.pk, guest_id)
        self.assertFalse(user.is_guest)
        self.assertEqual(ExamAttempt.objects.get(pk=attempt.pk).student, user)
        r = c.post(f"/exams/{self.reading2.pk}/start/")  # now everything is open
        self.assertTrue(r["Location"].startswith("/exams/attempt/"))

    def test_logging_in_moves_the_free_result(self):
        c, attempt = self._guest_take_one()
        guest_id = attempt.student_id
        r = c.post("/accounts/login/", {"username": self.student.email, "password": PASSWORD})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ExamAttempt.objects.get(pk=attempt.pk).student, self.student)
        self.assertFalse(User.objects.filter(pk=guest_id).exists())

    def test_guest_accounts_are_rate_limited_per_ip(self):
        from django.test import Client

        for _ in range(5):
            Client().post(f"/exams/{self.reading.pk}/start/")
        r = Client().post(f"/exams/{self.reading.pk}/start/")
        self.assertTrue(r["Location"].startswith("/accounts/register/"))
        self.assertEqual(User.objects.filter(is_guest=True).count(), 5)


class QuickEntryPaperFormatTests(TestCase):
    def test_listening_part1_as_printed_with_answer_key(self):
        from admin_dashboard.quick import parse_part
        from exams.models import ExamPart

        text = ("The listening paper is consist of six parts. Each recording will be played twice.\n"
                "Part 1\n"
                "1 \tA)\tPlease.\nB)\tYou are welcome.\nC)\tThat's all right.\n"
                "2 \tA)\tOh, have you?\nB)\tOh, don't they?\nC)\tOh, can they?\n"
                "ANSWERS: 1-C 2-A\n")
        items, errors = parse_part(text, ExamPart(cefr_part="L1"))
        self.assertEqual(errors, [])
        self.assertEqual([i.qtype for i in items], ["multiple_choice"] * 2)
        self.assertEqual(items[0].prompt, "Choose the correct answer.")
        self.assertEqual([o[1] for o in items[0].options], ["Please.", "You are welcome.", "That's all right."])
        self.assertEqual([[l for l, _, ok in i.options if ok] for i in items], [["C"], ["A"]])


class MapRequiredTests(BaseTest):
    def test_map_questions_need_a_map_picture(self):
        from exams.services import validate_publishable

        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/listening/new/", {"title": "L map", "time_limit": 35, "cefr_layout": "on"})
        exam = MockExam.objects.get(title="L map")
        part4 = exam.parts.get(cefr_part="L4")
        body = {"passage": "", "questions": "OPTIONS: A-H\n19. Quiet reading\n20. Computers\nANSWERS: 19-A 20-B"}
        preview = c.post(f"/admin-dashboard/parts/{part4.pk}/quick/", {**body, "action": "preview"}).content.decode()
        self.assertIn("Don't forget the map", preview)
        c.post(f"/admin-dashboard/parts/{part4.pk}/quick/", {**body, "action": "save"})
        self.assertEqual(part4.questions.count(), 2)
        self.assertTrue(any("upload the map picture" in p for p in validate_publishable(exam)))


class QuickEntryLetterAnswerTests(TestCase):
    def test_letter_f_is_an_option_in_matching_parts_not_false(self):
        from admin_dashboard.quick import parse_part
        from exams.models import ExamPart

        text = "7. Emma is organised. = F\n8. John is creative. = B\nTOPIC: JOB ADVERTISEMENTS\nA. one\nB. two\nF. six"
        items, errors = parse_part(text, ExamPart(cefr_part="R2"))
        self.assertEqual(errors, [])
        self.assertEqual([(i.qtype, i.answer) for i in items], [("matching", "F"), ("matching", "B")])
        items, errors = parse_part("List of headings\nA. x\nF. y\n15. Paragraph 1 = F", ExamPart(cefr_part="R3"))
        self.assertEqual((errors, items[0].qtype, items[0].answer), ([], "headings", "F"))
        items, errors = parse_part("23. The sky is green. = F", ExamPart(cefr_part="R4"))
        self.assertEqual((errors, items[0].answer), ([], "FALSE"))
        _, errors = parse_part("7. Emma = F", ExamPart(cefr_part="R2"))
        self.assertIn("the list of options is missing", errors[0])


class WholeMockImportTests(BaseTest):
    TEXT = (
        "Read the text. Fill in each gap with ONE word. You must use a word which is somewhere in the rest of the text.\n"
        "Part1\n"
        "The company that makes the famous little plastic bricks known as LEGO started as a small shop. At first the "
        "1.___________ sold wooden toys and other things and the 2._____________ grew quickly. PART 2\n"
        "Read the texts 7-14 and the statements A-J.\n"
        "1.\tThis expensive hotel is perfect for a romantic holiday.\n"
        "2.\tThis budget hotel is suitable for young people.\n"
        "A. THE ACE HOTEL\nBoutique hotel\nC. THE HYATT REGENCY\nUpscale hotel\nE. THE FOUR SEASONS\nHigh-end hotel\n"
        "PART 3\nList of Headings.\nA.\tRecognize Your Limitations\nB.\tTake a Rest\nC.\tClear Out Distractions\n"
        "15.\tParagraph 1 \t16. Paragraph 2\n"
        "I.\tThe overriding idea is to go for simplicity and a quiet basement or a library table allow you to focus "
        "on what you are doing instead of the kitchen table or common areas where you meet friends.\n"
        "II.\tMaking your work relate to your leisure activities or hobbies eliminates much of the tedium associated "
        "with it so whenever possible make your schoolwork centre around something you love.\n"
        "Part 4\nDavid Beckham\nDavid Beckham was born on May 2, 1975, in London. He played for Manchester United "
        "from 1992 to 2003 and every time he had a game he wore different football boots as a ritual for good luck.\n"
        "For questions 21-24, choose the correct answer A, B, C, or D.\n"
        "21. How many years had he played for Manchester United? A) 12 years\nB)\t10 years\n"
        "C)\t11 years    D) 13 years\n"
        "25. He wore the same boots in every game.\nA) True     B) False        C) No Information\n"
        "Part 5\nWorld Ecotourism\nEcotourism is not a nature 30_______________ but a 31_______________ tour and "
        "travellers enjoy it. Mark your answers on the answer sheet. 34. Which information is about South America?\n"
        "A)\tlocal education\nB)\tfungus\n")
    KEY = "1-shop 2-business | company\n3-C 4-A\n15 C, 16 B\n21-C 25-B\n30. adventure 31. sustainable 34-B"

    def test_preview_then_create(self):
        c = self.web(self.admin)
        url = "/admin-dashboard/mocks/section/reading/import/"
        self.assertEqual(c.get(url).status_code, 200)
        preview = c.post(url, {"action": "preview", "title": "Imported", "time_limit": 60, "text": self.TEXT,
                               "key": self.KEY}).content.decode()
        self.assertIn("Question numbers started again from 1", preview)
        self.assertFalse(MockExam.objects.filter(title="Imported").exists())
        r = c.post(url, {"action": "create", "title": "Imported", "time_limit": 60, "text": self.TEXT,
                         "key": self.KEY})
        exam = MockExam.objects.get(title="Imported")
        self.assertRedirects(r, f"/admin-dashboard/mocks/{exam.pk}/", fetch_redirect_response=False)
        q = {x.order: x for x in Question.objects.filter(exam=exam).prefetch_related("options")}
        self.assertEqual(sorted(q), [1, 2, 3, 4, 15, 16, 21, 25, 30, 31, 34])  # Part 2's 1–2 continue as 3–4
        self.assertEqual((q[1].question_type, q[1].correct_answer), ("gap_filling", "shop"))
        self.assertEqual(q[2].correct_answer, "business|company")
        self.assertEqual((q[3].question_type, q[3].correct_answer, q[3].options.count()), ("matching", "C", 3))
        self.assertEqual((q[16].question_type, q[16].correct_answer), ("headings", "B"))
        self.assertEqual([o.label for o in q[21].options.all() if o.is_correct], ["C"])
        self.assertEqual(q[21].options.count(), 4)
        self.assertEqual((q[25].question_type, q[25].correct_answer), ("true_false_not_given", "FALSE"))
        self.assertEqual((q[30].correct_answer, q[34].question_type), ("adventure", "multiple_choice"))
        parts = {p.cefr_part: p for p in exam.parts.all()}
        self.assertIn("(1) ______", parts["R1"].passage)
        self.assertIn("(30) ______", parts["R5"].passage)
        self.assertNotIn("Read the text", parts["R1"].passage)
        self.assertTrue(parts["R3"].passage.startswith("1. The overriding idea"))
        self.assertIn("David Beckham", parts["R4"].passage)
        self.assertNotIn("For questions", parts["R4"].passage)


class MatchingOptionsInTextBoxTests(BaseTest):
    def test_options_pasted_into_text_box_are_moved(self):
        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "R opts", "time_limit": 60, "cefr_layout": "on"})
        part2 = MockExam.objects.get(title="R opts").parts.get(cefr_part="R2")
        r = c.post(f"/admin-dashboard/parts/{part2.pk}/quick/", {
            "action": "save",
            "passage": "A. THE ACE HOTEL\nBoutique hotel\nC\tTHE HYATT REGENCY\nUpscale hotel\nE.  THE FOUR SEASONS",
            "questions": "7. This expensive hotel is perfect for a romantic holiday. = E\n8. A budget hotel. = A"})
        self.assertEqual(r.status_code, 302)
        q7 = part2.questions.get(order=7)
        self.assertEqual((q7.question_type, q7.correct_answer), ("matching", "E"))
        self.assertEqual([o.label for o in q7.options.all()], ["A", "C", "E"])
        self.assertEqual(q7.options.get(label="A").text, "THE ACE HOTEL Boutique hotel")
        part2.refresh_from_db()
        self.assertNotIn("ACE HOTEL", part2.passage)


class QuickEntryGapsFromTextTests(BaseTest):
    def test_gaps_in_text_become_questions_and_can_be_saved_without_answers(self):
        from exams.services import validate_publishable

        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "R gaps", "time_limit": 60, "cefr_layout": "on"})
        exam = MockExam.objects.get(title="R gaps")
        part1 = exam.parts.get(cefr_part="R1")
        url = f"/admin-dashboard/parts/{part1.pk}/quick/"
        body = {"passage": "At first the 1.___________ sold toys and the 2._____________ grew.", "questions": ""}
        preview = c.post(url, {**body, "action": "preview"}).content.decode()
        self.assertIn("2 questions ready", preview)
        self.assertIn("2 answers still missing", preview)
        r = c.post(url, {**body, "action": "save"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(part1.questions.values_list("order", "correct_answer")), [(1, ""), (2, "")])
        self.assertTrue(any("Question 1: set the correct answer" in p for p in validate_publishable(exam)))
        # adding just the answers later works
        c.post(url, {"passage": body["passage"], "questions": "1. shop\n2. business", "action": "save"})
        self.assertEqual(list(part1.questions.values_list("correct_answer", flat=True)), ["shop", "business"])


class QuickEntryWholePartInTextBoxTests(BaseTest):
    def test_part2_pasted_into_text_box_with_restarting_numbers(self):
        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "R p2", "time_limit": 60, "cefr_layout": "on"})
        exam = MockExam.objects.get(title="R p2")
        part1, part2 = exam.parts.get(cefr_part="R1"), exam.parts.get(cefr_part="R2")
        c.post(f"/admin-dashboard/parts/{part1.pk}/quick/", {"action": "save", "passage": "",
                                                             "questions": "1. a\n2. b\n3. c\n4. d\n5. e\n6. f"})
        passage = ("Read the texts 7-14 and the statements A-J.\n"
                   "1.\tThis expensive hotel is perfect for spending a romantic holiday.\n"
                   "2.\tThis budget hotel is suitable for young people.\n"
                   "A. THE ACE HOTEL\nBoutique hotel\nC. THE HYATT REGENCY\nUpscale hotel\nE. THE FOUR SEASONS\n")
        r = c.post(f"/admin-dashboard/parts/{part2.pk}/quick/", {"action": "save", "passage": passage,
                                                                 "questions": "ANSWERS: 7-E 8-A"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(part2.questions.values_list("order", "question_type", "correct_answer")),
                         [(7, "matching", "E"), (8, "matching", "A")])
        self.assertEqual(part2.questions.get(order=7).options.count(), 3)



class QuickEntryHotelsPart2Tests(BaseTest):
    PASSAGE = 'A. THE ACE HOTEL\nBoutique hotel\nPool, bar, live music, coffee shop\nPrices start at 150$\nIdeal for travellers.\n\nB. THE HILTON\nHotel chains\nFree Wi-fi, breakfast, meeting rooms\nPrices vary depending on location.\nPerfect for Business trips!\n\nC. THE HYATT REGENCY\nUpscale hotel\nPool, fitness centre, multiple dining options\nPrices start at 200$\nIdeal for budget travellers.\n\nD. MANDARIN ORIENTAL\nLuxury hotel\nSkyline view, spa, restaurant\nPrices start at 600$\nIdeal for travellers!\n\nE. THE FOUR SEASONS\nHigh-end hotel\nGolf course, tennis courts, restaurants\nPrices start at 700$\nIdeal for luxurious holidays!\n\nF. THE W HOTEL\nUpscale hotel\nNightclub, poolside cabana, ocean views\nPrices start at 300$\nBest for Parties!\n\nG. THE FAIRMONT\nHistoric hotel\nElegant décor, world-class service and dining options.\nPrices start at 400$\nPerfect for classical luxury fans.\n\nH. THE RITZ-CARLTON\nLuxury Hotel.\nSpa, Dining restaurant, Rooftop bar\nPrices start at 500$\nPerfect for a romantic gateway\n\nI. THE HOLIDAY INN\nAffordable hotel\nFree wi-fi and breakfast and multiple options\nPrices vary depending on options.\nIdeal for budget travellers.\n\nJ. THE ALOFT\nModern hotel\nKeyless room entry, mobile check in, free wifi\nPrices start at 100$\nIdeal for millennial travellers.\n\n\n\n\n\n7.\tThis expensive hotel is perfect for spending a romantic holiday.  \n8.\tThis budget hotel is suitable for young people who are looking for a nice and fun experience.  \n9.\tThis expensive hotel is suitable for families who are looking for a luxurious vacation.  \n10.\tThis moderate hotel is suitable for young people who wants to party a lot.  \n11.\tThis expensive hotel is suitable for directors and managers who often has a meeting. \n12.\tThis expensive hotel is perfect for people who prefer to have a nice scene from their rooms. \n13.\tThis budget hotel is ideal for travelers who wants to have a comfort without breaking their bank. \n14.\tThis expensive hotel is suitable for people who wants to have classic services.\n'
    QUESTIONS = '7. This expensive hotel is perfect for spending a romantic holiday. = H\n8. This budget hotel is suitable for young people who are looking for a nice and fun experience. = E\n9. This expensive hotel is suitable for families who are looking for a luxurious vacation. = C\n10. This moderate hotel is suitable for young people who wants to party a lot. = F\n11. This expensive hotel is suitable for directors and managers who often has a meeting. = B\n12. This expensive hotel is perfect for people who prefer to have a nice scene from their rooms. = D\n13. This budget hotel is ideal for travelers who wants to have a comfort without breaking their bank. = A\n14. This expensive hotel is suitable for people who wants to have classic services. = G\n'

    def test_user_part2_hotels(self):
        c = self.web(self.admin)
        c.post("/admin-dashboard/mocks/section/reading/new/", {"title": "Hotels", "time_limit": 60, "cefr_layout": "on"})
        part2 = MockExam.objects.get(title="Hotels").parts.get(cefr_part="R2")
        r = c.post(f"/admin-dashboard/parts/{part2.pk}/quick/",
                   {"action": "save", "passage": self.PASSAGE, "questions": self.QUESTIONS})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(part2.questions.values_list("order", "correct_answer")),
                         [(7, "H"), (8, "E"), (9, "C"), (10, "F"), (11, "B"), (12, "D"), (13, "A"), (14, "G")])
        q7 = part2.questions.get(order=7)
        self.assertEqual([o.label for o in q7.options.all()], list("ABCDEFGHIJ"))
        self.assertIn("Keyless room entry", q7.options.get(label="J").text)
        part2.refresh_from_db()
        self.assertNotIn("This expensive hotel", part2.passage)  # already a question, not repeated as text


class PublicMediaServedTests(BaseTest):
    def test_uploaded_picture_is_served_without_debug(self):
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        name = default_storage.save("exams/test-map.png", ContentFile(b"\x89PNG\r\n\x1a\nfake"))
        r = self.client.get(default_storage.url(name))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content)[:4], b"\x89PNG")
        self.assertIn(self.client.get("/media/../config/settings.py").status_code, (400, 404))  # never outside MEDIA_ROOT
        default_storage.delete(name)


class DeleteMockWithAttemptsTests(BaseTest):
    def test_mock_with_attempts_needs_the_confirmation_box(self):
        c = self.web(self.admin)
        exam = MockExam.objects.create(section="reading", title="Copy", time_limit=60, is_published=True)
        part = ExamPart.objects.create(exam=exam, title="P1", order=1)
        q = Question.objects.create(part=part, order=1, question_type="gap_filling", prompt="Gap 1", correct_answer="x")
        api = self.api(self.student)
        attempt = api.post(f"/api/exams/{exam.pk}/start/").json()["id"]
        api.patch(f"/api/attempts/{attempt}/answers/", {"answers": {str(q.pk): "x"}}, format="json")
        api.post(f"/api/attempts/{attempt}/submit/", {}, format="json")
        page = c.get(f"/admin-dashboard/mocks/{exam.pk}/delete/").content.decode()
        self.assertIn("1 attempt by 1 student will be deleted", page)
        c.post(f"/admin-dashboard/mocks/{exam.pk}/delete/", {})  # box not ticked
        self.assertTrue(MockExam.objects.filter(pk=exam.pk).exists())
        r = c.post(f"/admin-dashboard/mocks/{exam.pk}/delete/", {"with_attempts": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(MockExam.objects.filter(pk=exam.pk).exists())
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt).exists())


class MistakesNotebookTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.exam = MockExam.objects.create(title="Reading Mock", section="reading", time_limit=60, is_published=True)
        part = ExamPart.objects.create(exam=self.exam, title="Part 1", order=1,
                                       passage="The shop sold (1) ______ toys before it made bricks.")
        self.q_gap = Question.objects.create(part=part, order=1, question_type="gap_filling", prompt="Gap 1",
                                             correct_answer="wooden")
        self.q_tf = Question.objects.create(part=part, order=2, question_type="true_false_not_given", prompt="TF",
                                            correct_answer="TRUE")
        api = self.api(self.student)
        attempt_id = api.post(f"/api/exams/{self.exam.pk}/start/").json()["id"]
        api.post(f"/api/attempts/{attempt_id}/submit/", {"answers": {
            str(self.q_gap.pk): "plastic", str(self.q_tf.pk): "TRUE"}}, format="json")
        self.attempt_id = attempt_id

    def test_notebook_lists_wrong_answers_and_retry(self):
        c = self.web(self.student)
        r = c.get(reverse("dashboard:mistakes"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-qid="%d"' % self.q_gap.pk)
        self.assertNotContains(r, 'data-qid="%d"' % self.q_tf.pk)
        self.assertContains(r, "The shop sold")  # the gap's sentence is shown
        r = c.post(reverse("dashboard:mistake_check", args=[self.q_gap.pk]), {"answer": "Wooden"})
        self.assertTrue(r.json()["correct"])
        r = c.post(reverse("dashboard:mistake_check", args=[self.q_gap.pk]), {"answer": "metal"})
        self.assertFalse(r.json()["correct"])
        c.post(reverse("dashboard:mistake_learned", args=[self.q_gap.pk]))
        self.assertNotContains(c.get(reverse("dashboard:mistakes")), 'data-qid="%d"' % self.q_gap.pk)

    def test_cannot_check_questions_never_finished(self):
        r = self.web(self.other).post(reverse("dashboard:mistake_check", args=[self.q_gap.pk]), {"answer": "x"})
        self.assertEqual(r.status_code, 403)
        r = self.web(self.other).post(reverse("results:explain", args=[self.q_gap.pk]))
        self.assertEqual(r.status_code, 403)

    def test_ai_explanation_is_cached_per_language(self):
        from results.models import AnswerExplanation

        fake = FakeLLM()
        c = self.web(self.student)
        with mock.patch("ai.services.get_llm_provider", return_value=fake):
            r = c.post(reverse("results:explain", args=[self.q_gap.pk]), {"lang": "uz"})
            self.assertEqual(r.json()["text"], "The text says it directly.")
            c.post(reverse("results:explain", args=[self.q_gap.pk]), {"lang": "uz"})
            c.post(reverse("results:explain", args=[self.q_gap.pk]), {"lang": "en"})
        self.assertEqual(fake.calls.count("answer_explanation"), 2)
        self.assertIn("Uzbek", fake.systems[0])
        self.assertEqual(AnswerExplanation.objects.filter(question=self.q_gap).count(), 2)
        self.assertContains(c.get(reverse("results:detail", args=[self.attempt_id])), "data-why")

    def test_teacher_explanation_is_used_first(self):
        self.q_gap.explanation = "Line 1 says wooden."
        self.q_gap.save()
        r = self.web(self.student).post(reverse("results:explain", args=[self.q_gap.pk]))
        self.assertEqual(r.json(), {"text": "Line 1 says wooden.", "source": "teacher"})


class FeedbackLanguageTests(BaseTest):
    def test_writing_feedback_follows_student_language(self):
        from ai import prompts

        self.assertIn("Uzbek", prompts.writing_system_prompt("uz"))
        self.assertIn("English", prompts.speaking_system_prompt("en"))
        c = self.web(self.student)
        r = c.post(reverse("accounts:profile"), {"first_name": "S", "last_name": "T", "phone_number": "",
                                                 "feedback_language": "en"})
        self.assertIn(r.status_code, (200, 302))
        self.student.refresh_from_db()
        self.assertEqual(self.student.feedback_language, "en")


@override_settings(GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="secret",
                   GOOGLE_REDIRECT_URI="")
class GoogleLoginTests(BaseTest):
    def _sign_in(self, profile, client=None, nxt=""):
        c = client or self.client
        r = c.get(reverse("accounts:google_login") + (f"?next={nxt}" if nxt else ""))
        self.assertEqual(r.status_code, 302)
        self.assertIn("accounts.google.com", r["Location"])
        state = c.session["google_oauth"]["state"]
        with mock.patch("accounts.google.fetch_profile", return_value=profile):
            return c.get(reverse("accounts:google_callback"), {"code": "abc", "state": state})

    def test_button_only_when_configured(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "google-btn")
        with override_settings(GOOGLE_CLIENT_ID=""):
            self.assertNotContains(self.client.get(reverse("accounts:login")), "google-btn")
            self.assertEqual(self.client.get(reverse("accounts:google_login")).status_code, 404)

    def test_new_user_is_created_and_signed_in(self):
        r = self._sign_in({"email": "New.Person@gmail.com", "email_verified": True, "given_name": "New",
                           "family_name": "Person"}, nxt="/exams/")
        self.assertRedirects(r, "/exams/", fetch_redirect_response=False)
        user = User.objects.get(email="new.person@gmail.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_existing_user_signs_in(self):
        self._sign_in({"email": "student@example.com", "email_verified": True})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.student.pk)
        self.assertEqual(User.objects.filter(email="student@example.com").count(), 1)

    def test_bad_state_or_unverified_email_is_refused(self):
        self.client.get(reverse("accounts:google_login"))
        r = self.client.get(reverse("accounts:google_callback"), {"code": "abc", "state": "wrong"})
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self._sign_in({"email": "x@gmail.com", "email_verified": False})
        self.assertFalse(User.objects.filter(email="x@gmail.com").exists())
        self.assertNotIn("_auth_user_id", self.client.session)
