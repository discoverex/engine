UV_CACHE_DIR := $(CURDIR)/.cache/uv
export UV_CACHE_DIR

.PHONY: init sync test lint typecheck run smoke-torch smoke-hf

init:
	mkdir -p .cache/uv
	uv venv .venv
	uv sync --extra tracking --extra dev

sync:
	mkdir -p .cache/uv
	uv sync --extra tracking

lint:
	mkdir -p .cache/uv
	uv run --extra dev ruff check .

typecheck:
	mkdir -p .cache/uv
	uv run --extra dev mypy src tests

test:
	mkdir -p .cache/uv
	uv run --extra dev pytest -q

run:
	mkdir -p .cache/uv
	uv run $(ARGS)

smoke-torch:
	mkdir -p .cache/uv
	uv run --extra dev --extra tracking --extra ml-cpu pytest -q tests/test_tiny_model_pipeline_smoke.py -k tiny_torch

smoke-hf:
	mkdir -p .cache/uv
	uv run --extra dev --extra tracking --extra ml-cpu pytest -q tests/test_tiny_model_pipeline_smoke.py -k tiny_hf
