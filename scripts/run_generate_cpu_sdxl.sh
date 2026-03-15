#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ENGINE_ROOT}"

export UV_CACHE_DIR="${UV_CACHE_DIR:-${ENGINE_ROOT}/.cache/uv}"
export PYTHONUNBUFFERED=1
export DISCOVEREX_LOG_LEVEL="${DISCOVEREX_LOG_LEVEL:-INFO}"
export PREFECT_API_URL="${PREFECT_API_URL:-}"
export PREFECT_LOGGING_TO_API_ENABLED="${PREFECT_LOGGING_TO_API_ENABLED:-false}"
mkdir -p "${UV_CACHE_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed." >&2
  exit 1
fi

BACKGROUND_PROMPT="${BACKGROUND_PROMPT:-stormy harbor at dusk, cinematic hidden object puzzle background}"
BACKGROUND_NEGATIVE_PROMPT="${BACKGROUND_NEGATIVE_PROMPT:-blurry, low quality, artifact}"
OBJECT_PROMPT="${OBJECT_PROMPT:-hidden golden compass}"
OBJECT_NEGATIVE_PROMPT="${OBJECT_NEGATIVE_PROMPT:-blurry, low quality, artifact}"
FINAL_PROMPT="${FINAL_PROMPT:-polished playable hidden object scene}"
FINAL_NEGATIVE_PROMPT="${FINAL_NEGATIVE_PROMPT:-blurry, low quality, artifact}"
WIDTH="${WIDTH:-512}"
HEIGHT="${HEIGHT:-384}"

echo "[generate-cpu-sdxl] syncing uv environment with tracking + ml-cpu extras"
uv sync --extra tracking --extra ml-cpu

echo "[generate-cpu-sdxl] checking diffusers/transformers compatibility"
uv run python - <<'PY'
import sys

import transformers

version = getattr(transformers, "__version__", "unknown")
has_mt5 = hasattr(transformers, "MT5Tokenizer")
if version.startswith("5.") or not has_mt5:
    print(
        "[generate-cpu-sdxl] incompatible transformers runtime detected:",
        version,
        file=sys.stderr,
    )
    print(
        "[generate-cpu-sdxl] expected transformers>=4.46,<5.0 for diffusers SDXL adapters",
        file=sys.stderr,
    )
    raise SystemExit(2)
print(f"[generate-cpu-sdxl] transformers={version} compatible")
PY

echo "[generate-cpu-sdxl] running prompt-driven generate on CPU"
exec uv run discoverex generate \
  --verbose \
  --background-prompt "${BACKGROUND_PROMPT}" \
  --background-negative-prompt "${BACKGROUND_NEGATIVE_PROMPT}" \
  --object-prompt "${OBJECT_PROMPT}" \
  --object-negative-prompt "${OBJECT_NEGATIVE_PROMPT}" \
  --final-prompt "${FINAL_PROMPT}" \
  --final-negative-prompt "${FINAL_NEGATIVE_PROMPT}" \
  -o profile=generator_sdxl_gpu \
  -o runtime/model_runtime=cpu \
  -o "runtime.width=${WIDTH}" \
  -o "runtime.height=${HEIGHT}" \
  "$@"
