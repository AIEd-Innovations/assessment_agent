# Assessment Agent

FastAPI service in the AIEIC Lab Multi-Agent System. Grades a submission (any number of UTF-8 text files, in any
language) against the assignment's rubric with one LLM call, and runs an integrity check alongside it. Nothing is
executed. Grading is **synchronous**: several seconds to tens of seconds per student with a real provider.

## How grading works
1. Load the assignment's spec: rubric criteria with `max_points`, guidance, an optional reference solution and the
   `model` that grades every submission for that assignment.
2. One call to that model scores every criterion and writes the feedback, using the teacher's API key from the
   request. An unusable response is retried once.
3. `score` is the sum of the criterion scores, out of `max_score`.
4. `status` is `needs_review` (with `review_reasons`) if grading failed, the grader was unsure, the submission was
   truncated, or the integrity check rated the risk medium or high or found an attempt to influence the grade;
   otherwise `ai_graded`. An instructor's `final_score` replaces
   `score` and sets the status to `instructor_graded`.

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
| `DATA_DIR` | repo root (`/appdata` in the Docker image) | where results, anomaly reports and instructor-provided specs are written |
| `CURRICULUM_URL` | none | curriculum designer base URL, for importing approved labs |

**Deploying:** set `CORS_ORIGINS` to the origin of the deployed UI (for example `https://ui-instructor.vercel.app`). The default only allows the
local Vite dev server, so a deployed UI would be blocked by the browser even though the agent is healthy. `DATA_DIR` is created at startup and the
agent refuses to start if it cannot write there (in Docker the process runs as uid 1000, so a bind-mounted host folder must be writable by that user).

## Grading specs
A spec holds `title`, `description`, `criteria` (`id`, `name`, `description`, `max_points`, and an optional
`expected_answer` for quiz-style questions), `guidance`, `skill_level` (used by the integrity check) and `model` (one of
the models above; `claude-sonnet-5-5` if omitted). It can also have a reference solution or answer key, and course
materials such as lecture notes. Solutions, materials and expected answers are given to the grader but never returned by
the API.

Instructors manage specs through the API (endpoints below); they are stored in `DATA_DIR/assignments/<id>/` and take
precedence over the built-in examples in `assessment_agent/assignments/` (`hw1_sorting`, `hw2_linked_list`, drafts for
an instructor to check). Solutions and materials can be text in any language, PDF, Word `.docx` or Jupyter `.ipynb`;
the extracted text is what the grader reads, and the originals are kept. Up to 40,000 characters of materials are given
to the grader, and the upload response warns when there is more.

An approved curriculum designer lab can be imported with `POST /assignments/import/{lab_id}` (set `CURRICULUM_URL`).
The import is a saved copy, so grading never depends on the curriculum designer: its criterion weights are scaled to
100 points (the code/report/manual split is ignored), its quiz becomes a separate `<id>-quiz` assignment with the
expected answers, and its uploaded material becomes course material. Re-importing replaces the rubric and keeps any
uploaded solution.

### Seed data for UI development
Results are stored as JSON files in the repo root (gitignored). To have something to list without grading anything:

```bash
cp demo/seed_results.json assessment_results.json
curl "localhost:8000/results?assignment_id=hw1_sorting"
```
`demo/seed_results.json` was made with the mock model and edited by hand to cover each status.

## Docker
```bash
docker build -t assessment-agent .
docker run -p 8000:8000 -e CORS_ORIGINS=http://localhost:5173 -v assessment-data:/appdata assessment-agent
```
The image runs as an unprivileged user and writes results to `/appdata` (mount a volume to keep them).

## Endpoints
| Method and path | Purpose |
|---|---|
| `GET /health` | health check |
| `POST /submit` | multipart: `student_id`, `assignment_id`, one or more `files` (UTF-8 text); header `X-LLM-API-Key` |
| `POST /submit-json` | JSON: `student_id`, `assignment_id`, `files: [{filename, content}]`; header `X-LLM-API-Key` |
| `GET /models` | supported models with their vendor, and the default |
| `GET /assignments`, `/assignments/{id}/rubric` | assignments with a spec; the rubric view never includes the solution, materials or expected answers |
| `PUT /assignments/{id}`, `DELETE /assignments/{id}` | create or replace a rubric (JSON), or delete an uploaded assignment |
| `PUT /assignments/{id}/solution` | multipart `files`: replace the reference solution or answer key |
| `POST`/`GET /assignments/{id}/materials`, `DELETE /assignments/{id}/materials/{name}` | add, list or remove course materials |
| `POST /assignments/import/{lab_id}?assignment_id=` | import an approved curriculum designer lab (and its quiz) |
| `GET /results?student_id&assignment_id&status`, `/results/{submission_id}`, `/results/{submission_id}/provenance` | graded results |
| `POST /results/{submission_id}/review` | JSON: `final_score` (0 to `max_score`) and `notes`; replaces the AI score |
| `GET /anomalies?reviewed` | anomaly reports |

Key result fields: `criteria` (per-criterion score, justification and evidence), `score`, `max_score`, `status`,
`review_reasons`, `final_score`, `feedback`, `model` and `mock`. The full shape is `AssessmentResult` in `models.py`.

## Known limitations (not yet addressed)
- Only UTF-8 text files are accepted, and only their names and a hash are stored.
- Code is read, not run, so subtle bugs can be missed.
- No regrade endpoint, no CSV export, no student names (only `student_id`), no authentication.
- The assignment endpoints are not protected yet: anyone who can reach the agent can change a rubric.
- Re-submitting appends a new result rather than replacing the old one.

## Tests
```bash
pip install pytest pytest-asyncio httpx
pytest
```
