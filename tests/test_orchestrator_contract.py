from __future__ import annotations

import pytest

from discoverex.orchestrator_contract import (
    EngineJobV1,
    EngineJobV2,
    JobSpec,
    build_cli_tokens,
    build_worker_entrypoint,
)


def test_engine_job_v1_requires_command_specific_args() -> None:
    with pytest.raises(ValueError, match="background_asset_ref or background_prompt"):
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
            "config_name": "verify_prod",
            "config_dir": "/tmp/conf",
            "args": {"scene_json": "/tmp/scene.json"},
            "overrides": ["a=1", "b=2"],
        }
    )

    assert build_cli_tokens(job) == [
        "discoverex",
        "verify",
        "--config-name",
        "verify_prod",
        "--config-dir",
        "/tmp/conf",
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
        "uv run discoverex generate --background-asset-ref bg://dummy" in entrypoint[2]
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


def test_engine_job_v2_accepts_animate_without_required_args() -> None:
    job = EngineJobV2.model_validate(
        {
            "contract_version": "v2",
            "command": "animate",
            "args": {},
        }
    )
    assert build_cli_tokens(job) == ["discoverex", "animate"]


def test_engine_job_v2_accepts_background_prompt_without_asset_ref() -> None:
    job = EngineJobV2.model_validate(
        {
            "contract_version": "v2",
            "command": "generate",
            "args": {"background_prompt": "a beach at dawn"},
        }
    )
    assert build_cli_tokens(job) == [
        "discoverex",
        "generate",
        "--background-prompt",
        "a beach at dawn",
    ]


def test_job_spec_requires_canonical_inputs() -> None:
    job_spec = JobSpec.model_validate(
        {
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
            "inputs": {
                "contract_version": "v2",
                "command": "generate",
                "args": {"background_asset_ref": "bg://dummy"},
            },
        }
    )
    assert job_spec.inputs is not None
    assert job_spec.inputs.command == "generate"
    assert job_spec.engine_run.command == "generate"


def test_engine_job_v2_accepts_inline_resolved_config() -> None:
    job = EngineJobV2.model_validate(
        {
            "contract_version": "v2",
            "command": "generate",
            "resolved_config": {
                "models": {
                    "background_generator": {"_target_": "pkg.Background"},
                    "hidden_region": {"_target_": "pkg.Hidden"},
                    "inpaint": {"_target_": "pkg.Inpaint"},
                    "perception": {"_target_": "pkg.Perception"},
                    "fx": {"_target_": "pkg.Fx"},
                },
                "adapters": {
                    "artifact_store": {"_target_": "pkg.Artifacts"},
                    "metadata_store": {"_target_": "pkg.Metadata"},
                    "tracker": {"_target_": "pkg.Tracker"},
                    "scene_io": {"_target_": "pkg.SceneIo"},
                    "report_writer": {"_target_": "pkg.ReportWriter"},
                },
                "runtime": {},
                "thresholds": {},
                "model_versions": {},
            },
            "args": {"background_prompt": "a beach at dawn"},
        }
    )
    assert job.resolved_config is not None
