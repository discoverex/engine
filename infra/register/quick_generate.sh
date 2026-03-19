#!/usr/bin/env bash
set -euo pipefail

ENGINE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTER_ENV="${ENGINE_ROOT}/infra/register/.env"
ENGINE_REF="${ENGINE_REF:-dev}"

if [[ ! -f "${REGISTER_ENV}" ]]; then
  echo "missing env file: ${REGISTER_ENV}" >&2
  exit 1
fi

set -a
source "${REGISTER_ENV}"
set +a

cd "${ENGINE_ROOT}"

python3 -m infra.register.register_prefect_job \
  --job-name quick-generate-1-https \
  --command generate \
  --execution-profile generator-pixart-gpu \
  --repo-url https://github.com/discoverex/engine.git \
  --ref "${ENGINE_REF}" \
  --background-prompt "stormy harbor at dusk, cinematic hidden object puzzle background" \
  --background-negative-prompt "blurry, low quality, artifact" \
  --object-prompt "banana" \
  --object-negative-prompt "blurry, low quality, artifact" \
  --final-prompt "polished playable hidden object scene" \
  --final-negative-prompt "blurry, low quality, artifact" \
  --checkpoint-dir /tmp \
  --mlflow-tracking-uri "${MLFLOW_TRACKING_URI}" \
  --aws-access-key-id "${MINIO_ACCESS_KEY}" \
  --aws-secret-access-key "${MINIO_SECRET_KEY}" \
  --artifact-bucket "${ARTIFACT_BUCKET}" \
  --cf-access-client-id "${cf_access_client_id}" \
  --cf-access-client-secret "${cf_access_client_secret}" \
  -o runtime.width=1024 \
  -o runtime.height=1024

python3 -m infra.register.register_prefect_job \
  --job-name quick-generate-2-https \
  --command generate \
  --execution-profile generator-pixart-gpu \
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
  --cf-access-client-id "${cf_access_client_id}" \
  --cf-access-client-secret "${cf_access_client_secret}" \
  -o runtime.width=1024 \
  -o runtime.height=1024
