# Assessment Agent

FastAPI service in the AIEIC Lab Multi-Agent System. Grades a submission (any number of UTF-8 text files, in any
language) against the assignment's rubric with one LLM call, and runs an integrity check alongside it. Nothing is
executed. Grading is **synchronous**: several seconds to tens of seconds per student with a real provider.

## How grading works
1. Load the assignment's spec: rubric criteria with `max_points`, guidance and an optional reference solution.
2. One LLM call scores every criterion and writes the feedback. An unusable response is retried once.
3. `score` is the sum of the criterion scores, out of `max_score`.
4. `status` is `needs_review` (with `review_reasons`) if grading failed, the grader was unsure, the submission was
   truncated or the integrity risk is medium or high; otherwise `ai_graded`. An instructor's `final_score` replaces
   `score` and sets the status to `instructor_graded`.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py            # http://localhost:8000  (API docs at /docs)
python demo/run_demo.py  # grade the demo submissions from the command line
```

### LLM provider (`DEFAULT_LLM_PROVIDER`)
| Value | Needs | Notes |
|---|---|---|
| `claude_cli` (default) | the `claude` CLI installed and logged in | shells out per call |
| `anthropic` | `ANTHROPIC_API_KEY` | model is hard-coded in `llm/anthropic_api.py` |
| `fake` | nothing | offline canned responses: every criterion gets 80%. For demos and UI development |

Settings can go in a `.env` file (loaded at startup) or the shell environment:

| Variable | Default | Purpose |
|---|---|---|
| `DEFAULT_LLM_PROVIDER` | `claude_cli` | see above |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated origins allowed to call the API from a browser |
| `ANTHROPIC_API_KEY` | none | for `anthropic` |
| `DATA_DIR` | repo root (`/appdata` in the Docker image) | where results and anomaly reports are written |

## Grading specs
`assessment_agent/assignments/<assignment_id>/spec.json` holds `title`, `description`, `criteria` (`id`, `name`,
`description`, `max_points`) and `guidance`. An optional `solution/` folder holds reference files, which are never
returned by the API. The hw1 and hw2 specs are drafts for an instructor to check. Specs will later come from the
curriculum designer, whose rubric format will need mapping in `spec.py`.

### Seed data for UI development
Results are stored as JSON files in the repo root (gitignored). To have something to list without grading anything:

```bash
cp demo/seed_results.json assessment_results.json
curl "localhost:8000/results?assignment_id=hw1_sorting"
```
`demo/seed_results.json` was made with the `fake` provider and edited by hand to cover each status.

## Docker
```bash
docker build -t assessment-agent .
docker run -p 8000:8000 -e DEFAULT_LLM_PROVIDER=fake -e CORS_ORIGINS=http://localhost:5173 -v assessment-data:/appdata assessment-agent
```
The image runs as an unprivileged user and writes results to `/appdata` (mount a volume to keep them). It does **not** contain the
`claude` CLI, so the default provider will not work in it: use `anthropic` (with `ANTHROPIC_API_KEY`) or `fake`.

## Endpoints
| Method and path | Purpose |
|---|---|
| `GET /health` | health check |
| `POST /submit` | multipart: `student_id`, `assignment_id`, one or more `files` (UTF-8 text) |
| `POST /submit-json` | JSON: `student_id`, `assignment_id`, `files: [{filename, content}]` |
| `GET /assignments`, `/assignments/{id}/rubric` | assignments with a spec; the rubric view never includes the solution |
| `GET /results?student_id&assignment_id&status`, `/results/{submission_id}`, `/results/{submission_id}/provenance` | graded results |
| `POST /results/{submission_id}/review` | JSON: `final_score` (0 to `max_score`) and `notes`; replaces the AI score |
| `GET /anomalies?reviewed` | anomaly reports |

Key result fields: `criteria` (per-criterion score, justification and evidence), `score`, `max_score`, `status`,
`review_reasons`, `final_score` and `feedback`. The full shape is `AssessmentResult` in `models.py`.

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
