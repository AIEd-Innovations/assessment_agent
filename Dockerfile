FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Results, the review queue and anomaly reports are written to DATA_DIR: mount a volume here to keep them.
# Student code is executed by the sandbox as a subprocess, so run as an unprivileged user.
ENV DATA_DIR=/appdata
RUN useradd --create-home app && mkdir -p /appdata && chown app /appdata
USER app

EXPOSE 8000

# The default LLM provider (claude_cli) needs the claude CLI, which is not in this image.
# Set DEFAULT_LLM_PROVIDER=anthropic (with ANTHROPIC_API_KEY) or =fake for demos.
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8000"]
