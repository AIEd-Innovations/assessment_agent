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
| `DATA_DIR` | repo root (`/appdata` in the Docker image) | where results and anomaly reports are written |

**Deploying:** set `CORS_ORIGINS` to the origin of the deployed UI (for example `https://ui-instructor.vercel.app`). The default only allows the
local Vite dev server, so a deployed UI would be blocked by the browser even though the agent is healthy. `DATA_DIR` is created at startup and the
agent refuses to start if it cannot write there (in Docker the process runs as uid 1000, so a bind-mounted host folder must be writable by that user).

## Grading specs
`assessment_agent/assignments/<assignment_id>/spec.json` holds `title`, `description`, `criteria` (`id`, `name`,
`description`, `max_points`), `guidance` and `skill_level` (what students are expected to know, used by the integrity
check) and `model` (one of the models above; `claude-sonnet-5-5` if omitted). An optional `solution/` folder holds reference files, which are never
returned by the API. The hw1 and hw2 specs are drafts for an instructor to check. Specs will later come from the
curriculum designer, whose rubric format will need mapping in `spec.py`.

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
| `GET /assignments`, `/assignments/{id}/rubric` | assignments with a spec; the rubric view never includes the solution |
| `GET /results?student_id&assignment_id&status`, `/results/{submission_id}`, `/results/{submission_id}/provenance` | graded results |
| `POST /results/{submission_id}/review` | JSON: `final_score` (0 to `max_score`) and `notes`; replaces the AI score |
| `GET /anomalies?reviewed` | anomaly reports |

Key result fields: `criteria` (per-criterion score, justification and evidence), `score`, `max_score`, `status`,
`review_reasons`, `final_score`, `feedback`, `model` and `mock`. The full shape is `AssessmentResult` in `models.py`.

## Known limitations (not yet addressed)
- Only UTF-8 text files are accepted, and only their names and a hash are stored.
- Code is read, not run, so subtle bugs can be missed.
- No regrade endpoint, no CSV export, no student names (only `student_id`), no authentication.
- Specs are files on disk, and re-submitting appends a new result rather than replacing the old one.

## Tests
```bash
pip install pytest pytest-asyncio httpx
pytest
```
