# Build from the repo root: docker build -f pipeline/ingest/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/common ./pipeline/common
COPY pipeline/ingest ./pipeline/ingest
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.ingest.main:app", "--host", "0.0.0.0", "--port", "8080"]
