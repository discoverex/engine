#!/usr/bin/env bash
set -euo pipefail

retry() {
  local max_retries="$1"
  local delay_secs="$2"
  shift 2
  local attempt=1
  until "$@"; do
    if [ "$attempt" -ge "$max_retries" ]; then
      return 1
    fi
    attempt=$((attempt + 1))
    sleep "$delay_secs"
  done
}

run_apt() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

export UV_CACHE_DIR="${PWD}/.cache/uv"
mkdir -p "${UV_CACHE_DIR}"

if [ -e ".venv" ] && [ ! -w ".venv" ]; then
  echo "error: .venv is not writable by $(id -un)."
  echo "fix: run 'sudo chown -R $(id -un):$(id -gn) .venv' on host and retry."
  exit 1
fi

retry 3 5 run_apt apt-get update
retry 3 5 run_apt apt-get install -y curl python3 python3-pip
if ! command -v uv >/dev/null 2>&1; then
  retry 3 5 bash -lc "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

UV_BIN="${HOME}/.local/bin/uv"
if [ ! -x "${UV_BIN}" ]; then
  UV_BIN="$(command -v uv)"
fi

if [ ! -d ".venv" ]; then
  retry 3 5 "${UV_BIN}" venv .venv
fi
retry 3 5 "${UV_BIN}" sync --extra dev
