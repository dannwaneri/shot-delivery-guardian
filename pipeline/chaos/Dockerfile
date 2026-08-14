# Build from the repo root: docker build -f pipeline/chaos/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/chaos ./pipeline/chaos
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.chaos.main:app", "--host", "0.0.0.0", "--port", "8080"]
