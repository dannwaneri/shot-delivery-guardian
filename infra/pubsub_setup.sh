#!/usr/bin/env bash
# Creates the Pub/Sub topics and push subscriptions that wire the pipeline
# stages together. Run once per GCP project, after infra/deploy.sh has
# created the Cloud Run services (subscriptions need real push-endpoint URLs).
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

TOPICS=(shot-render shot-color shot-qc shot-delivery)
for topic in "${TOPICS[@]}"; do
  gcloud pubsub topics create "$topic" --project "$PROJECT_ID" || true
done

create_push_subscription() {
  local sub="$1" topic="$2" service="$3"
  local service_url
  service_url=$(gcloud run services describe "shot-${service}" \
    --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')
  gcloud pubsub subscriptions create "$sub" \
    --topic "$topic" \
    --push-endpoint "${service_url}/pubsub/push" \
    --project "$PROJECT_ID" || true
}

create_push_subscription shot-render-sub shot-render render
create_push_subscription shot-color-sub shot-color color
create_push_subscription shot-qc-sub shot-qc qc
create_push_subscription shot-delivery-sub shot-delivery delivery

echo "Topics and push subscriptions created."
