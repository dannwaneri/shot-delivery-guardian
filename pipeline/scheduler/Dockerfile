# Build from the repo root: docker build -f pipeline/scheduler/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/common ./pipeline/common
COPY pipeline/scheduler ./pipeline/scheduler
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.scheduler.main:app", "--host", "0.0.0.0", "--port", "8080"]
