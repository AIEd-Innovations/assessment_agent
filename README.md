# Assessment Agent

FastAPI service in the AIEIC Lab Multi-Agent System. Grades a submission (any number of UTF-8 text files, in any
language) against the assignment's rubric with one LLM call. Nothing is executed. Grading is **synchronous**: several
seconds to tens of seconds per student with a real provider.

## How grading works
1. Load the assignment's spec: rubric criteria with `max_points`, guidance, an optional reference solution and the
   `model` that grades every submission for that assignment.
2. One call to that model scores every criterion and writes the feedback, using the teacher's API key from the
   request. An unusable response is retried once.
3. `score` is the sum of the criterion scores, out of `max_score`.
4. `status` is `needs_review` (with `review_reasons`) if grading failed, the grader was unsure or saw an attempt to
   influence the grade, or the submission was truncated; otherwise `ai_graded`. An instructor's `final_score` replaces
   `score` and sets the status to `instructor_graded`.
5. An instructor can have a submission graded again (`POST /results/{id}/regrade`), optionally with notes for the
   grader. It uses the assignment's current rubric, solution, materials and model, and saves a **new** result with
   `regrade_of` set; the original result is never changed. A regrade that fails saves nothing (502).

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py            # http://localhost:8000  (API docs at /docs)
python demo/run_demo.py  # grade the demo submissions from the command line
```

### Models and API keys
Teachers grade on their own credits. Each grading request carries the teacher's API key in the `X-LLM-API-Key`
header; it is used for that request only and never stored or logged. The key must belong to the vendor of the
assignment's model:

| Vendor | Models (`GET /models`) |
|---|---|
| Anthropic | `claude-opus-5-5`, `claude-sonnet-5-5` (default), `claude-haiku-5-5` |
| OpenAI | `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna` |
| Google Gemini | `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.5-flash-lite` |

**Without a key, an offline mock model grades the submission** (every criterion gets 80%). The result has
`"mock": true`, `"model": "mock"`, status `needs_review` and a review reason saying no key was provided, so it is never
mistaken for a real grade. A key the vendor rejects returns 401 and no result is saved.

Settings can go in a `.env` file (loaded at startup) or the shell environment:

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated origins allowed to call the API from a browser |
| `MONGODB_URI` | required | Atlas connection string for the Assessment Agent database user; keep it out of the repo |
| `MONGODB_DB` | `aied` | shared MongoDB database name |
| `CURRICULUM_URL` | none | curriculum designer base URL, for importing approved labs |
| `AUTH_MS_CLIENT_ID` | none (sign-in off) | the instructor UI's Microsoft app (client) ID; when set, every endpoint except `/health` needs a signed-in instructor |
| `AUTH_MS_TENANT_ID` | Cal Poly's tenant | the Microsoft directory sign-ins must come from |
| `AUTH_ALLOWED_EMAIL_DOMAIN` | `calpoly.edu` | the only email domain let in |

**Sign-in:** with `AUTH_MS_CLIENT_ID` set, requests need `Authorization: Bearer <Microsoft ID token>`, which the instructor UI
sends once someone signs in. The token's signature (Microsoft's published keys), audience, issuer, Cal Poly tenant, expiry and
email domain are checked (`auth.py`); anything else gets 401 with the reason. Without it the API is open, as for local development.

**Deploying:** set `CORS_ORIGINS` to the origin of the deployed UI (for example `https://ui-instructor.vercel.app`). The default only allows the
local Vite dev server, so a deployed UI would be blocked by the browser even though the agent is healthy. Set `MONGODB_URI` only in the deployment
environment; it is never committed. Before deployment, Vishal must run `scripts/init_db.py` and `scripts/atlas_roles.py` from the shared databases repo.

## Grading specs
A spec holds `title`, `description`, `criteria` (`id`, `name`, `description`, `max_points`, and an optional
`expected_answer` for quiz-style questions), `guidance` and `model` (one of
the models above; `claude-sonnet-5-5` if omitted). It can also have a reference solution or answer key, and course
materials such as lecture notes. Solutions, materials and expected answers are given to the grader but never returned by
the API.

Instructors manage specs through the API (endpoints below). They are stored in the shared MongoDB `aied` database and
are scoped to a `course_id`; the same assignment ID can therefore be used in different courses without exposing or
overwriting another instructor's data. The bundled examples in `assessment_agent/assignments/` are test fixtures only,
not production defaults. Solutions and materials can be text in any language, PDF, Word `.docx` or Jupyter `.ipynb`;
the extracted text is what the grader reads, and the originals are kept. Up to 40,000 characters of materials are given
to the grader, and the upload response warns when there is more.

Each assignment, built-in examples included, can also have grading preferences (`/assignments/{id}/agent-config`):
feedback tone (Encouraging, Neutral, Direct), feedback detail (Brief, Standard, Detailed), partial credit (Generous,
Balanced, Strict) and free-text notes. The defaults leave the grading prompt unchanged; anything else is added to it
as instructions, and partial credit is the one setting that can change scores. Preferences use the shared
`agent_configs` collection, count toward the spec hash, and are deleted with the assignment.

An approved curriculum designer lab can be imported with `POST /assignments/import/{lab_id}` (set `CURRICULUM_URL`).
The import is a saved copy, so grading never depends on the curriculum designer: its criterion weights are scaled to
100 points (the code/report/manual split is ignored), its quiz becomes a separate `<id>-quiz` assignment with the
expected answers, and its uploaded material becomes course material. Re-importing replaces the rubric and keeps any
uploaded solution.

### Seed data for UI development
Initialize the shared database with `scripts/init_db.py` from the shared `databases` repository, then create an
assignment through the API or import an approved curriculum lab. Results, submitted files, assignments, materials and
agent settings all live in MongoDB, scoped by `course_id`.

## Docker
```bash
docker build -t assessment-agent .
docker run -p 8000:8000 -e CORS_ORIGINS=http://localhost:5173 -e MONGODB_URI='mongodb+srv://…' assessment-agent
```
The image runs as an unprivileged user. Persistent data is held in MongoDB; no local data volume is needed.

## Endpoints
| Method and path | Purpose |
|---|---|
| `GET /health` | health check |
| `POST /submit` | multipart: `course_id`, `student_id`, `assignment_id`, one or more `files` (UTF-8 text); header `X-LLM-API-Key` |
| `POST /submit-json` | query `course_id`; JSON: `student_id`, `assignment_id`, `files: [{filename, content}]`; header `X-LLM-API-Key` |
| `GET /models` | query `course_id`; supported models with their vendor and the default |
| `GET /assignments`, `/assignments/{id}/rubric` | query `course_id`; assignments with a spec; the rubric view never includes the solution, materials or expected answers |
| `PUT /assignments/{id}`, `DELETE /assignments/{id}` | query `course_id`; create or replace a rubric (JSON), or delete an assignment |
| `GET`/`PUT /assignments/{id}/agent-config` | query `course_id`; the instructor's grading preferences: `tone`, `feedback_detail`, `partial_credit`, `notes` |
| `PUT /assignments/{id}/solution` | query `course_id`; multipart `files`: replace the reference solution or answer key |
| `POST`/`GET /assignments/{id}/materials`, `DELETE /assignments/{id}/materials/{name}` | query `course_id`; add, list or remove course materials |
| `POST /assignments/import/{lab_id}?course_id=&assignment_id=` | import an approved curriculum designer lab (and its quiz) |
| `GET /results?course_id=&student_id&assignment_id&status&latest`, `/results/{submission_id}`, `/results/{submission_id}/provenance` | graded results; `course_id` is required on every results request and `latest=true` keeps only each student's newest result per assignment |
| `POST /results/{submission_id}/regrade` | query `course_id`; optional JSON `instructions`; header `X-LLM-API-Key`. Grades the stored files again as a new result |
| `POST /results/{submission_id}/review` | query `course_id`; JSON: `final_score` (0 to `max_score`) and `notes`; replaces the AI score |

Key result fields: `criteria` (per-criterion score, justification and evidence), `score`, `max_score`, `status`,
`review_reasons`, `final_score`, `feedback`, `model`, `mock`, and `regrade_of` and `regrade_instructions` on a regrade.
The full shape is `AssessmentResult` in `models.py`.

## Stored student work
Submitted files are kept in MongoDB so they can be regraded. No endpoint returns their contents. When Microsoft
sign-in is enabled, the caller's SSO subject is resolved through the shared `users` and `courses` collections; an
instructor can only access courses they own. Results from before this migration may not have stored files and cannot
be regraded (409); resubmit them.

## Known limitations (not yet addressed)
- Only UTF-8 text files are accepted.
- Code is read, not run, so subtle bugs can be missed.
- No bulk regrade, no CSV export, no student names (only `student_id`).
- Local development with `AUTH_MS_CLIENT_ID` unset intentionally skips Microsoft sign-in and ownership checks. Enable
  sign-in outside local development to enforce course ownership.

## Tests
```bash
pip install pytest pytest-asyncio httpx
pytest
```
