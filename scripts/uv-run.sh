#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${PWD}/.cache/uv"
mkdir -p "${UV_CACHE_DIR}"

if [ -e ".venv" ] && [ ! -w ".venv" ]; then
  echo "error: .venv is not writable by $(id -un)." >&2
  echo "fix: sudo chown -R $(id -un):$(id -gn) .venv" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  uv venv .venv
fi

uv "$@"
