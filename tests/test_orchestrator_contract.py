from __future__ import annotations

import pytest

from discoverex.orchestrator_contract import (
    EngineJobV1,
    build_cli_tokens,
    build_worker_entrypoint,
)


def test_engine_job_v1_requires_command_specific_args() -> None:
    with pytest.raises(ValueError, match="missing required args"):
        EngineJobV1.model_validate(
            {
                "contract_version": "v1",
                "command": "gen-verify",
                "args": {},
            }
        )


def test_build_cli_tokens_preserves_override_order() -> None:
    job = EngineJobV1.model_validate(
        {
            "contract_version": "v1",
            "command": "verify-only",
            "args": {"scene_json": "/tmp/scene.json"},
            "overrides": ["a=1", "b=2"],
        }
    )

    assert build_cli_tokens(job) == [
        "discoverex",
        "verify-only",
        "--scene-json",
        "/tmp/scene.json",
        "-o",
        "a=1",
        "-o",
        "b=2",
    ]


def test_build_worker_entrypoint_wraps_uv_run() -> None:
    job = EngineJobV1.model_validate(
        {
            "contract_version": "v1",
            "command": "gen-verify",
            "args": {"background_asset_ref": "bg://dummy"},
        }
    )

    entrypoint = build_worker_entrypoint(job)
    assert entrypoint[0:2] == ["/bin/sh", "-lc"]
    assert (
        "uv run discoverex gen-verify --background-asset-ref bg://dummy"
        in entrypoint[2]
    )


def test_job_runtime_deduplicates_extras() -> None:
    job = EngineJobV1.model_validate(
        {
            "contract_version": "v1",
            "command": "gen-verify",
            "args": {"background_asset_ref": "bg://dummy"},
            "runtime": {"extras": ["tracking", "storage", "tracking", ""]},
        }
    )
    assert job.runtime.extras == ["tracking", "storage"]
