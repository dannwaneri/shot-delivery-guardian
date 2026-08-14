# Build from the repo root: docker build -f pipeline/delivery/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/common ./pipeline/common
COPY pipeline/delivery ./pipeline/delivery
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.delivery.main:app", "--host", "0.0.0.0", "--port", "8080"]
