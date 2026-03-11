#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_ENV="${ROOT_DIR}/../orchestrator/.env"
ENGINE_REF="${ENGINE_REF:-dev}"

if [[ ! -f "${ORCH_ENV}" ]]; then
  echo "missing env file: ${ORCH_ENV}" >&2
  exit 1
fi

set -a
source "${ORCH_ENV}"
export PREFECT_CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-}"
export PREFECT_CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-}"
set +a

cd "${ROOT_DIR}"

python3 scripts/register_prefect_job.py \
  --job-name quick-generate-1-https \
  --command generate \
  --execution-profile generator-sdxl-gpu \
  --repo-url https://github.com/discoverex/engine.git \
  --ref "${ENGINE_REF}" \
  --background-prompt "stormy harbor at dusk, cinematic hidden object puzzle background" \
  --background-negative-prompt "blurry, low quality, artifact" \
  --object-prompt "hidden golden compass" \
  --object-negative-prompt "blurry, low quality, artifact" \
  --final-prompt "polished playable hidden object scene" \
  --final-negative-prompt "blurry, low quality, artifact" \
  --checkpoint-dir /tmp \
  --mlflow-tracking-uri "${MLFLOW_TRACKING_URI}" \
  --aws-access-key-id "${MINIO_ACCESS_KEY}" \
  --aws-secret-access-key "${MINIO_SECRET_KEY}" \
  --artifact-bucket "${ARTIFACT_BUCKET}" \
  --cf-access-client-id "${CF_ACCESS_CLIENT_ID}" \
  --cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET}" \
  -o runtime.width=512 \
  -o runtime.height=384

python3 scripts/register_prefect_job.py \
  --job-name quick-generate-2-https \
  --command generate \
  --execution-profile generator-sdxl-gpu \
  --repo-url https://github.com/discoverex/engine.git \
  --ref "${ENGINE_REF}" \
  --background-prompt "ancient observatory interior at night, cinematic hidden object puzzle background" \
  --background-negative-prompt "blurry, low quality, artifact" \
  --object-prompt "hidden silver astrolabe" \
  --object-negative-prompt "blurry, low quality, artifact" \
  --final-prompt "polished playable hidden object scene" \
  --final-negative-prompt "blurry, low quality, artifact" \
  --checkpoint-dir /tmp \
  --mlflow-tracking-uri "${MLFLOW_TRACKING_URI}" \
  --aws-access-key-id "${MINIO_ACCESS_KEY}" \
  --aws-secret-access-key "${MINIO_SECRET_KEY}" \
  --artifact-bucket "${ARTIFACT_BUCKET}" \
  --cf-access-client-id "${CF_ACCESS_CLIENT_ID}" \
  --cf-access-client-secret "${CF_ACCESS_CLIENT_SECRET}" \
  -o runtime.width=512 \
  -o runtime.height=384
