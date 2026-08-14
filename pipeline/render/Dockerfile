# Build from the repo root: docker build -f pipeline/render/Dockerfile -t <tag> .
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/common ./pipeline/common
COPY pipeline/render ./pipeline/render
ENV PYTHONPATH=/app
CMD ["uvicorn", "pipeline.render.main:app", "--host", "0.0.0.0", "--port", "8080"]
