# Assessment Agent

FastAPI service in the AIEIC Lab Multi-Agent System. Grades student submissions (code + optional report), flags anomalies,
generates feedback, and queues submissions for instructor review. Grading is **synchronous**: each submission makes several
LLM calls, so expect tens of seconds per student with a real provider.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py            # http://localhost:8000  (API docs at /docs)
```

### LLM provider (`DEFAULT_LLM_PROVIDER`)
| Value | Needs | Notes |
|---|---|---|
| `claude_cli` (default) | the `claude` CLI installed and logged in | shells out per call |
| `anthropic` | `ANTHROPIC_API_KEY` | model is hard-coded in `llm/anthropic_api.py` |
| `fake` | nothing | offline canned responses; scores come from exact-match test execution only. For demos and UI development |

Settings can go in a `.env` file (loaded at startup) or the shell environment:

| Variable | Default | Purpose |
|---|---|---|
| `DEFAULT_LLM_PROVIDER` | `claude_cli` | see above |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated origins allowed to call the API from a browser |
| `ANTHROPIC_API_KEY` | none | for `anthropic` |
| `DATA_DIR` | repo root (`/appdata` in the Docker image) | where results, the review queue and anomaly reports are written |

### Seed data for UI development
Results are stored as JSON files in the repo root (gitignored). To have something to list without grading anything:

```bash
cp demo/seed_results.json assessment_results.json
curl "localhost:8000/results?assignment_id=hw1_sorting"
```
`demo/seed_results.json` was produced by running the demo submissions through the real pipeline with the `fake` provider;
two records were then edited by hand (one high-risk anomaly, one high review priority) so the UI has varied statuses.

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
| `POST /submit` | multipart: `student_id`, `assignment_id`, `code_file?`, `report_file?` (UTF-8 text) |
| `POST /submit-json` | JSON: `student_id`, `assignment_id`, `code?`, `report?` |
| `GET /assignments`, `/assignments/{id}/test-cases`, `/assignments/{id}/rubric` | assignment definitions (files in `assessment_agent/assignments/`) |
| `GET /results?student_id&assignment_id`, `/results/{submission_id}`, `/results/{submission_id}/provenance` | graded results |
| `GET /review-queue`, `POST /review-queue/{submission_id}/complete` | instructor manual review (`instructor_score` 0-10, `notes`) |
| `GET /anomalies?reviewed` | anomaly reports |

## Known limitations (not yet addressed)
- The submitted code and report text are not stored, only hashes.
- No regrade endpoint, no CSV export, no student names (only `student_id`), no authentication.
- Assignments are files on disk; there is no API to create one and no reference-solution or quiz support.
- Re-submitting a student appends a new result rather than replacing the old one.
- The sandbox is a subprocess with an import blocklist, not strong isolation.

## Tests
```bash
pip install pytest pytest-asyncio
pytest
```
