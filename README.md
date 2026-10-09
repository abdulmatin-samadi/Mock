# DREAMZONE — Multilevel (CEFR) learning and mock exam platform

Django + Django REST Framework + PostgreSQL. Students take Reading, Listening, Writing and Speaking mock exams (single sections or a full
mock) in the Multilevel (CEFR) format, with server-side scoring and AI evaluation of essays and
recordings. Admins manage everything from a separate dashboard. Roles: student and admin.

---

## 1. Quick start

The repository has two folders:

```
backend/    Django project (pages, API, database, AI) → deploy to Render
frontend/   public/static (CSS, JS, images) + build.sh → deploy to Netlify (netlify.toml)
render.yaml Render blueprint (web service + PostgreSQL); netlify.toml Netlify config
```

Django still renders every page; it reads the CSS/JS/images from `frontend/public/static`.
On Netlify the static files are served from its CDN and every other request is proxied to the
Render backend, so the site works on the Netlify domain exactly as it does locally.

```bash
cd /Users/abdulmatin/Desktop/mock
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend                        # every manage.py command runs from here

createdb bandwise                 # PostgreSQL database
cp .env.example .env              # then set SECRET_KEY, DB_*, AI_API_KEY, STT_API_KEY

python manage.py migrate
python manage.py createsuperuser  # becomes role=admin automatically
python manage.py seed_cefr            # 2 Multilevel mocks per section + 2 full mocks (listening audio via macOS TTS)
python manage.py seed_words           # starter list for the Word of the day card
python manage.py runserver
```

| URL | What |
|---|---|
| http://127.0.0.1:8000/ | Public site / student area |
| /dashboard/ | Student dashboard |
| /admin-dashboard/ | Admin dashboard (admins only) |
| /api/ | REST API (JWT or session) |
| /django-admin/ | Built-in Django admin (admins only; scores are read-only) |

Run the tests: `python manage.py test core` (24 tests: scoring, full Reading/Writing/Speaking flows with
AI test doubles, recording privacy, role isolation, JWT, and rendering of every page per role).

### AI configuration (`.env`)

| Variable | Meaning |
|---|---|
| `AI_PROVIDER` | `anthropic` (default), `openai` or `gemini` — evaluates essays and speaking transcripts |
| `AI_API_KEY` | key for that provider (server-side only, never sent to the browser) |
| `AI_MODEL` | optional; default `claude-opus-5-5` (anthropic) / `gpt-4o` (openai) / `gemini-3.5-flash` (gemini) |
| `AI_EFFORT` | Anthropic reasoning effort (`low`…`max`, default `high`) |
| `STT_PROVIDER` / `STT_API_KEY` / `STT_MODEL` | speech-to-text; `openai` (`whisper-1`, `gpt-4o-transcribe`…) or `gemini` (`gemini-3.5-flash`). Anthropic has no STT API, so with `AI_PROVIDER=anthropic` you still need an OpenAI or Gemini key here for Speaking. With `gemini` for both, one key (from https://aistudio.google.com/apikey) covers everything |
| `AI_TASK_MODE` | `thread` (background pool, default), `sync` (inline), `queue` (only `manage.py process_ai_queue`) |

Without keys the platform still works; AI submissions are saved and marked **failed** with a clear
message (never a fake score). After adding keys, retry from the admin pages or run
`python manage.py process_ai_queue --retry-failed`.

With the Anthropic provider and a model that supports it, requests opt into Anthropic's server-side
refusal fallback (`fallbacks: "default"`), so a safety-classifier decline is retried on a fallback model
instead of failing.

---

## 2. Architecture

```
Browser (HTML/CSS/vanilla JS)            Mobile / external clients
   │  session + CSRF                          │  JWT (Bearer)
   ▼                                          ▼
Django views (templates)  ◄──────────►  DRF API (/api/…)  — serializers, permissions, filters
   │                                          │
   └────────────► services.py (business logic: grading, progress, attempts) ◄──┘
                         │                         │
                         ▼                         ▼
                  PostgreSQL (ORM)          ai/ AIService ──► providers (Anthropic / OpenAI / Gemini / Whisper)
                         │                         ▲
                  Storage: public media     ai/tasks.py background jobs (thread pool or
                  + private media           `process_ai_queue` command; Celery-ready)
                  (S3-compatible ready)
```

Design rules applied everywhere:
- **Business logic lives in `services.py`**, not in views. Views and API endpoints are thin.
- **All scoring is server-side.** Clients send raw answers / essays / audio; correctness, raw score,
  percentage, Multilevel 0–75 score and CEFR level are computed on the server. Score fields
  are read-only in every API and in Django admin.
- **AI is behind one interface** (`ai/services.py: AIService.evaluate_writing / transcribe_speaking /
  evaluate_speaking`). Providers implement `ai/providers/base.py`; swap with an env var.
- **Private files are never public.** Recordings and listening audio live in a
  separate `private` storage and are streamed only through permission-checked views (with HTTP Range
  support for seeking; optional nginx `X-Accel-Redirect`).

## 3. Folder structure

Inside `backend/` (static files are in `frontend/public/static/`):

```
config/            settings, root urls, api_urls (all /api/ routes)
core/              validators (file type/size/magic bytes), private media streaming, permissions,
                   role mixins, pagination, template tags, home page, tests, seed_cefr + seed_words commands
accounts/          custom User (email login, student/admin roles), auth views + JWT API, role groups
exams/             MockExam, ExamPart (passage/section), Question, Option, WritingTask,
                   SpeakingQuestion; scoring.py (0–75 scale, CEFR, answer matching); exam rooms
results/           ExamAttempt, Answer, Result; services.py = attempt lifecycle + all scoring
writing/           WritingSubmission, WritingEvaluation; AI evaluation job
speaking/          SpeakingSubmission, SpeakingEvaluation; upload, STT + AI job, secure audio
ai/                AIService, providers (anthropic, openai, gemini, whisper), prompts, JSON schemas,
                   background runner, process_ai_queue command
dashboard/         student dashboard (stats, charts, word of the day), results, writing/speaking history
admin_dashboard/   admin web dashboard + /api/admin/ API, shared filtering services
templates/         base.html (site), portal_base.html (admin), per-app templates
static/css/app.css design system; static/js/{app,exam,writing,speaking,misc}.js
```

Reading and Listening share one model set (`ExamPart` + `Question` + `Option`) inside `exams/`
because their structure and grading are identical; their section-specific behaviour (passage pane vs.
audio player) is keyed on `MockExam.section`.

## 4. Data model

```
User (email unique, role student|admin, profile fields)
 └─1:N─ ExamAttempt(exam, status, started/submitted, score, percentage, time_spent, counts)
          ├─1:N─ Answer(question, answer, selected_option, is_correct, points)
          ├─1:1─ Result(score, scaled_score(0–75), cefr_level, feedback, details JSON)
          ├─1:N─ WritingSubmission(task, essay, word_count, status, score) ─1:1─ WritingEvaluation
          └─1:N─ SpeakingSubmission(question, audio_file, duration, processing_status,
                                    transcript, score) ─1:1─ SpeakingEvaluation

MockExam(title, section reading|listening|writing|speaking, level,
         time_limit, audio, transcript, is_published)
 ├─1:N─ ExamPart(passage | audio, transcript) ─1:N─ Question(type, prompt, correct_answer, points)
 │                                                    └─1:N─ Option(label, text, is_correct)
 ├─1:N─ WritingTask(task_type task1_1|task1_2|task2, topic, min words, image)
 └─1:N─ SpeakingQuestion(part 1|2|3, question, cue_card_points, preparation_time, speaking_time)
```

Every submission carries the student FK, so first name, last name, email, exam, section, date, score
and status are always available (rendered by `templates/partials/identity.html`).

## 5. Flows

**Authentication.** Web: email + password session login (CSRF-protected forms), register, logout (POST),
forgot/reset password (email link — console backend in development), change password, profile edit.
API: `POST /api/auth/login/` → `{access, refresh}` JWT; refresh rotates and blacklists; logout blacklists.
Nobody can self-register as admin; users cannot change their own role.

**Student.** Register → dashboard (stats, learning curve, level by skill, word of the day) → pick a
section or a full mock → start (attempt created server-side with a server deadline) → answer → submit →
result page; history pages for results, writing and speaking.

**Admin.** `/admin-dashboard/` → statistics → users (search/filter, full profile with every result,
essay, recording, transcript, full mock sitting) → Reading/Listening/Writing/Speaking mocks
(create, edit, delete, publish with validation, duplicate, manage questions) → writing submissions,
speaking recordings, all results (filters: section, type, status, date range, score range) → settings
(AI config status, queue processing).

**Mock exam (Reading/Listening).** `start` → server stores `started_at`; deadline = start + time limit.
Answers autosave every 15 s (`PATCH /api/attempts/{id}/answers/`). `submit` grades every question on the
server (MCQ by option, TFNG/YNNG and matching by label, completion/short answer by normalised text with
`|`-separated alternatives). After deadline + grace, late answers are ignored and only autosaved answers
are graded. Percentage → Multilevel 0–75 → CEFR
(B1 38–50, B2 51–64, C1 65–75).

**Writing + AI.** Student writes (live word count, local draft backup, timer) → submit → one
`WritingSubmission` per task is saved → a background job calls `AIService.evaluate_writing()` →
structured JSON (criterion scores, grammar/vocabulary mistakes, rewrites, weak/strong sentences,
suggestions) is validated, clamped and the overall 0–75 score recomputed on the server → `WritingEvaluation`
saved → attempt result aggregated (mean of Task 1.1, 1.2 and 2) → result page auto-refreshes.

**Speaking recording.** Browser asks for microphone → per question: preparation countdown → automatic
MediaRecorder recording with countdown and level meter → stop → replay → re-record or submit → upload
(`multipart`) → server validates extension + magic bytes + size and stores it privately.

**Speaking + AI.** Background job: speech-to-text → transcript saved → `AIService.evaluate_speaking()`
on the transcript → `SpeakingEvaluation` saved → when the student finishes the test, criteria are averaged
into the attempt result. **Pronunciation is not scored and is explicitly labelled “Not assessed”**,
because the configured providers evaluate a transcript, not the audio. A provider that genuinely
analyses audio can set `supports_audio_pronunciation = True`.

**Full mock.** Admin bundles one Listening, Reading, Writing and Speaking mock into a `FullMock`
(`/admin-dashboard/full-mocks/`; publishing requires all four section mocks to be published). The student
starts a `FullMockAttempt` and takes the sections in the official order from a progress page; each section
is a normal `ExamAttempt` linked to the sitting (with its own timer, and you can break between sections).
When all four are completed — including AI evaluation of Writing/Speaking — the overall score is the
mean of the four 0–75 section scores, converted to CEFR (`results.services.refresh_full_attempt`).

## 6. REST API

All endpoints require authentication unless noted; list endpoints support `?page=`, `?search=`,
`?ordering=` and field filters.

| Endpoint | Description |
|---|---|
| `POST /api/auth/register/` *(public)* | create a student account → tokens |
| `POST /api/auth/login/` *(public)* | `{email, password}` → `{access, refresh}` |
| `POST /api/auth/token/refresh/`, `/api/auth/logout/` | rotate / blacklist refresh token |
| `POST /api/auth/password/change/`, `/reset/`, `/reset/confirm/` | password management |
| `GET/PATCH /api/users/me/` | own profile (role/email read-only) |
| `/api/exams/`, `/api/exams/reading/`, `/listening/`, `/writing/`, `/speaking/` | published mocks (no correct answers); `start`, `audio` actions |
| `/api/exams/full/` | published full mocks; `start` action creates/resumes a sitting |
| `/api/attempts/full/` | own full mock sittings with per-section status; `next` action starts the next section |
| `/api/attempts/` | own attempts; `answers` (autosave) and `submit` actions |
| `/api/answers/`, `/api/results/` | own answers (correctness revealed after grading) and results |
| `/api/writing/submissions/`, `/api/writing/evaluations/` | essays (POST `{task, essay}`), AI evaluations |
| `/api/speaking/submissions/`, `/api/speaking/evaluations/` | recordings (multipart POST), `audio` stream, evaluations |
| `/api/admin/users/` | admin user CRUD, `?role=&is_active=&search=`, `report` action |
| `/api/admin/exams/` (+ `exam-parts/`, `questions/`, `writing-tasks/`, `speaking-questions/`) | full mock management incl. answers; `publish`, `unpublish`, `duplicate` |
| `/api/admin/full-mocks/` | full mock CRUD; `publish`, `unpublish` |
| `/api/admin/results/`, `/api/admin/writing-submissions/`, `/api/admin/speaking-submissions/` | all results/submissions with `?section=&type=&status=&date_from=&date_to=&min_score=&max_score=&q=`; `retry` actions |

Example:
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email":"student@example.com","password":"..."}' | python -c 'import sys,json;print(json.load(sys.stdin)["access"])')
curl -s -X POST localhost:8000/api/exams/1/start/ -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/api/attempts/1/submit/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"answers": {"12": "TRUE", "13": "library"}}'
```

## 7. Security summary

- Role checks + object-level permissions on every view and endpoint (students ↔ own data only;
  admin-only dashboard/API). Django Groups (Students/Admins) carry model
  permissions and are synced with the role.
- CSRF on all forms and session-authenticated `fetch()` calls; JWT for API clients; auth endpoints
  rate-limited; AI submissions rate-limited.
- Uploads: extension allow-list, per-type size limits, content sniffing (magic bytes / Pillow
  verification), random server-side filenames.
- Private media streamed only after permission checks; another student's recording returns 403/404.
- Secrets only in environment variables; production settings enable secure cookies, HSTS, SSL redirect.

## 8. Production notes

- Run with gunicorn behind nginx; `python manage.py collectstatic`; set `DEBUG=False`, `SECRET_KEY`,
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and a real `EMAIL_BACKEND`.
- Serve `/media/` (public) from nginx. For private files either stream through Django (default) or set
  `PRIVATE_MEDIA_X_ACCEL=/protected/` with an nginx `internal` location pointing at `PRIVATE_MEDIA_ROOT`.
- S3-compatible storage: `pip install django-storages[s3]`, set `USE_S3=True` and the `AWS_*` variables.
- AI jobs: the default thread pool is fine for one server. For several workers set `AI_TASK_MODE=queue`
  and run `python manage.py process_ai_queue` every minute (cron/systemd), or swap `ai/tasks.enqueue`
  for Celery — callers don't change.

## 9. Deploy: backend on Render, frontend on Netlify

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/abdulmatin-samadi/Mock)
[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/abdulmatin-samadi/Mock)

Step-by-step guide (Uzbek): [DEPLOY.md](DEPLOY.md).

- `render.yaml` creates the `dreamzone-samadi-api` web service (root `backend/`) and the `dreamzone-db`
  PostgreSQL database. It asks for `ADMIN_EMAIL`, `ADMIN_PASSWORD` (the admin is created on start —
  Render's free plan has no shell) and `AI_API_KEY`.
- `netlify.toml` publishes `frontend/public` and `frontend/build.sh` writes a proxy rule that sends every
  other request to `BACKEND_URL` (default `https://dreamzone-samadi-api.onrender.com`).
- Uploaded files: Render's free disk is wiped on every restart. Set `USE_S3=True` and the `AWS_*`
  variables (e.g. a free Cloudflare R2 bucket) to keep audio, pictures and recordings.

## 10. Known limitations

- Pronunciation is not assessed by the bundled providers (clearly labelled in results).
- Recording duration is reported by the browser (used for display/prompting only, never for scoring).
- AI scores are estimates from a language model, not official Multilevel results.
