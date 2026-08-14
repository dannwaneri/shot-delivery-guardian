# Build from the repo root: docker build -f pipeline/qc/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/common ./pipeline/common
COPY pipeline/qc ./pipeline/qc
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.qc.main:app", "--host", "0.0.0.0", "--port", "8080"]
