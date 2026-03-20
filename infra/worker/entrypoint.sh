#!/usr/bin/env sh
set -eu

log() {
  printf '%s | discoverex-worker | %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

if [ "${PREFECT_CLIENT_CUSTOM_HEADERS:-}" = "" ]; then
  unset PREFECT_CLIENT_CUSTOM_HEADERS || true
fi

eval "$(
  python -m infra.worker.client_env shell --default-queue "${PREFECT_WORK_QUEUE:-gpu-fixed}"
)"

POOL="${PREFECT_WORK_POOL:-discoverex-fixed}"
PRIMARY_QUEUE="${PREFECT_WORK_QUEUE:-gpu-fixed}"
BATCH_QUEUE="${PREFECT_BATCH_WORK_QUEUE:-${PRIMARY_QUEUE}-batch}"
WORK_QUEUES="${PREFECT_WORK_QUEUES:-${PRIMARY_QUEUE},${BATCH_QUEUE}}"
WORKER_LIMIT="${PREFECT_WORKER_LIMIT:-1}"
RUNTIME_ROOT="${DISCOVEREX_WORKER_RUNTIME_DIR:-/var/lib/discoverex}"
CACHE_DIR="${DISCOVEREX_CACHE_DIR:-${RUNTIME_ROOT}/cache}"
CHECKPOINT_DIR="${ORCHESTRATOR_CHECKPOINT_DIR:-${RUNTIME_ROOT}/checkpoints}"
MODEL_CACHE_DIR="${MODEL_CACHE_DIR:-${CACHE_DIR}/models}"
UV_CACHE_DIR="${UV_CACHE_DIR:-${CACHE_DIR}/uv}"
SUMMARY="$(
  python -m infra.worker.client_env summary --default-queue "${PRIMARY_QUEUE}"
)"

export DISCOVEREX_WORKER_RUNTIME_DIR="${RUNTIME_ROOT}"
export DISCOVEREX_CACHE_DIR="${CACHE_DIR}"
export ORCHESTRATOR_CHECKPOINT_DIR="${CHECKPOINT_DIR}"
export MODEL_CACHE_DIR="${MODEL_CACHE_DIR}"
export UV_CACHE_DIR="${UV_CACHE_DIR}"
export HF_HOME="${HF_HOME:-${MODEL_CACHE_DIR}/hf}"
export PYTHONPATH="/app:/app/src:${PYTHONPATH:-}"

mkdir -p "${CHECKPOINT_DIR}" "${CACHE_DIR}" "${MODEL_CACHE_DIR}" "${UV_CACHE_DIR}" "${HF_HOME}"

python -c "from infra.worker.work_queues import ensure_work_pool_and_queues; ensure_work_pool_and_queues(work_pool='${POOL}', primary_queue='${PRIMARY_QUEUE}', batch_queue='${BATCH_QUEUE}')"

set -- prefect worker start --pool "${POOL}" --type process --limit "${WORKER_LIMIT}"
OLD_IFS="${IFS}"
IFS=','
for queue in ${WORK_QUEUES}; do
  if [ -n "${queue}" ]; then
    set -- "$@" --work-queue "${queue}"
  fi
done
IFS="${OLD_IFS}"

log "startup summary: ${SUMMARY}"
log "watched queues: ${WORK_QUEUES}"
log "launching: $*"

exec "$@"
