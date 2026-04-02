set shell := ["bash", "-cu"]

uv_cache_dir := justfile_directory() + "/.cache/uv"
path := "."
line_limit := "200"

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
    just type "."

test p="tests":
    just _ensure-cache
    uv run --extra dev pytest {{p}}

check p=path:
    just linecheck
    just lint {{p}}
    just type {{p}}
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


linecheck:
    #!/usr/bin/env bash
    set -euo pipefail

    limit="{{line_limit}}"
    python3 - <<'PY'
    from pathlib import Path
    import sys

    limit = int("{{line_limit}}")
    exceptions = {
        "src/discoverex/adapters/inbound/cli/main.py",
        "src/discoverex/adapters/outbound/models/dummy.py",
        "src/discoverex/adapters/outbound/models/hf_yolo_clip.py",
        "src/discoverex/adapters/outbound/models/sdxl_background_generation.py",
        "src/discoverex/adapters/outbound/models/sdxl_final_render.py",
        "src/discoverex/adapters/outbound/models/sdxl_inpaint.py",
        "src/discoverex/application/use_cases/gen_verify/orchestrator.py",
        "src/discoverex/domain/services/verification.py",
        "src/discoverex/flows/generate.py",
        "src/discoverex/orchestrator_contract/launcher.py",
    }
    offenders = []
    for path in Path("src/discoverex").rglob("*.py"):
        path_str = str(path)
        if path_str in exceptions:
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > limit:
            offenders.append(f"ERROR: {path_str} ({line_count} lines > {limit})")
    if offenders:
        print("\n".join(offenders))
        print("Line limit exceeded")
        sys.exit(1)
    PY
