set shell := ["bash", "-cu"]

uv_cache_dir := justfile_directory() + "/.cache/uv"
path := "."

export UV_CACHE_DIR := uv_cache_dir

@_ensure-cache:
    mkdir -p "{{uv_cache_dir}}"

init:
    just _ensure-cache
    uv venv .venv
    uv sync --extra tracking --extra dev

sync:
    just _ensure-cache
    uv sync --extra tracking

lint p=path:
    just _ensure-cache
    uv run --extra dev ruff check {{p}}

format p=path:
    just _ensure-cache
    uv run --extra dev ruff format {{p}}

type p=path:
    just _ensure-cache
    uv run --extra dev mypy {{p}}

typecheck:
    just type "src tests"

test p="tests":
    just _ensure-cache
    uv run --extra dev pytest {{p}}

check p=path:
    just lint {{p}}
    just typecheck
    just test

run *args:
    just _ensure-cache
    uv run {{args}}

smoke-torch:
    just _ensure-cache
    uv run --extra dev --extra tracking --extra ml-cpu pytest -q tests/test_tiny_model_pipeline_smoke.py -k tiny_torch

smoke-hf:
    just _ensure-cache
    uv run --extra dev --extra tracking --extra ml-cpu pytest -q tests/test_tiny_model_pipeline_smoke.py -k tiny_hf
