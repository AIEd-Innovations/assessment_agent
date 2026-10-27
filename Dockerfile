FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Results and instructor-provided specs are written to DATA_DIR: mount a volume here to keep them.
ENV DATA_DIR=/appdata
RUN useradd --create-home app && mkdir -p /appdata && chown app /appdata
USER app

EXPOSE 8000

# Teachers send their API key with each grading request; without one the offline mock model grades.
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8000"]
