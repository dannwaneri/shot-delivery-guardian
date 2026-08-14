# Build from the repo root: docker build -f agent/Dockerfile -t <tag> .
#
# agent/main.py execs the `mcp-grafana` binary as a subprocess (stdio MCP
# transport). It is not a Python package, so it can't come from
# requirements.txt — this stage builds it from source with the real,
# documented command from github.com/grafana/mcp-grafana, then the final
# stage copies just the binary in.
FROM golang:1.23-alpine AS mcp-grafana-builder
# mcp-grafana's go.mod can require a newer Go than this base image ships.
# GOTOOLCHAIN=auto lets `go install` fetch whatever version it needs instead
# of failing on a version mismatch (confirmed necessary — the base image's
# Go 1.23 failed against mcp-grafana's Go >=1.26.3 requirement).
ENV GOTOOLCHAIN=auto
RUN go install github.com/grafana/mcp-grafana/cmd/mcp-grafana@latest

FROM python:3.12-slim
WORKDIR /app
COPY --from=mcp-grafana-builder /go/bin/mcp-grafana /usr/local/bin/mcp-grafana
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent ./agent
ENV PYTHONPATH=/app
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
