#!/usr/bin/env bash
# Builds and deploys every pipeline service, the chaos injector, and the
# agent to Cloud Run. Run infra/pubsub_setup.sh afterward to wire the topics
# to the freshly deployed service URLs (subscriptions need the URLs to exist
# first).
#
# Builds locally with Docker and pushes straight to Artifact Registry's
# gcr.io-compatible host, rather than `gcloud builds submit --tag`, because
# that command has no way to point at a non-default Dockerfile path
# (confirmed - `gcloud builds submit --tag ... -f <dockerfile>` fails with
# "unrecognized arguments: -f"), and every service here needs its own
# Dockerfile from a shared repo-root build context.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-us-central1}"
GRAFANA_OTLP_ENDPOINT="${GRAFANA_OTLP_ENDPOINT:?set GRAFANA_OTLP_ENDPOINT}"
GRAFANA_INSTANCE_ID="${GRAFANA_INSTANCE_ID:?set GRAFANA_INSTANCE_ID}"
GRAFANA_OTLP_TOKEN="${GRAFANA_OTLP_TOKEN:?set GRAFANA_OTLP_TOKEN}"

gcloud auth configure-docker gcr.io --quiet --project "$PROJECT_ID"

deploy_pipeline_service() {
  local name="$1" dockerfile="$2" extra_env="${3:-}"
  local image="gcr.io/${PROJECT_ID}/shot-${name}"
  local env_vars="GCP_PROJECT_ID=${PROJECT_ID},OTLP_ENDPOINT=${GRAFANA_OTLP_ENDPOINT},GRAFANA_INSTANCE_ID=${GRAFANA_INSTANCE_ID},GRAFANA_OTLP_TOKEN=${GRAFANA_OTLP_TOKEN}"
  if [ -n "$extra_env" ]; then
    env_vars="${env_vars},${extra_env}"
  fi
  docker build -f "$dockerfile" -t "$image" .
  docker push "$image"
  gcloud run deploy "shot-${name}" \
    --image "$image" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --allow-unauthenticated \
    --set-env-vars "$env_vars"
}

deploy_pipeline_service scheduler pipeline/scheduler/Dockerfile
deploy_pipeline_service ingest pipeline/ingest/Dockerfile
deploy_pipeline_service render pipeline/render/Dockerfile
deploy_pipeline_service color pipeline/color/Dockerfile
deploy_pipeline_service qc pipeline/qc/Dockerfile
deploy_pipeline_service delivery pipeline/delivery/Dockerfile

# chaos needs to know where ingest and scheduler actually live - read the
# real URLs back from Cloud Run instead of hardcoding them, so a full
# re-run of this script never regresses into a placeholder-URL state.
ingest_url=$(gcloud run services describe shot-ingest --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
scheduler_url=$(gcloud run services describe shot-scheduler --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
deploy_pipeline_service chaos pipeline/chaos/Dockerfile "INGEST_URL=${ingest_url}/ingest,SCHEDULER_URL=${scheduler_url}/shots"

GRAFANA_STACK_URL="${GRAFANA_STACK_URL:?set GRAFANA_STACK_URL}"
GRAFANA_SERVICE_ACCOUNT_TOKEN="${GRAFANA_SERVICE_ACCOUNT_TOKEN:?set GRAFANA_SERVICE_ACCOUNT_TOKEN}"

agent_image="gcr.io/${PROJECT_ID}/shot-agent"
docker build -f agent/Dockerfile -t "$agent_image" .
docker push "$agent_image"
gcloud run deploy shot-agent \
  --image "$agent_image" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars "GRAFANA_STACK_URL=${GRAFANA_STACK_URL},GRAFANA_SERVICE_ACCOUNT_TOKEN=${GRAFANA_SERVICE_ACCOUNT_TOKEN},GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION}"

echo "Done. Now run infra/pubsub_setup.sh to wire topics/subscriptions to these URLs."
