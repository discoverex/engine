from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "register_orchestrator_job.py"
)


def test_register_script_dry_run_builds_repo_job_spec() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--command",
            "generate",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--background-asset-ref",
            "bg://dummy",
            "-o",
            "adapters/artifact_store=minio",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_mode"] == "repo"
    assert payload["repo_url"] == "https://github.com/example/engine.git"
    assert (
        payload["entrypoint"][2]
        == "PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher"
    )
    assert payload["engine_run"]["contract_version"] == "v2"
    assert payload["engine_run"]["command"] == "generate"
    assert payload["engine_run"]["config_name"] == "generate"
    assert payload["engine_run"]["config_dir"] == "conf"
    assert payload["engine_run"]["args"]["background_asset_ref"] == "bg://dummy"
    assert payload["engine_run"]["overrides"] == ["adapters/artifact_store=minio"]
    assert payload["job_name"] == "generate--generate--none"


def test_register_script_requires_command_specific_args() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--command",
            "verify",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "--scene-json is required for command=verify" in proc.stderr


def test_register_script_accepts_background_prompt_only() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--command",
            "generate",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--background-prompt",
            "misty mountain lake",
            "--object-prompt",
            "small hidden red lantern",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["args"]["background_prompt"] == "misty mountain lake"
    assert payload["engine_run"]["args"]["object_prompt"] == "small hidden red lantern"
    assert payload["engine_run"]["config_name"] == "generate"


def test_register_script_accepts_v1_command_when_version_is_v1() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--contract-version",
            "v1",
            "--command",
            "gen-verify",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--background-asset-ref",
            "bg://dummy",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["contract_version"] == "v1"
    assert payload["engine_run"]["command"] == "gen-verify"
    assert payload["engine_run"]["config_name"] == "gen_verify"


def test_register_script_local_tiny_profile_adds_worker_overrides_and_env() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--execution-profile",
            "local-tiny-cpu",
            "--command",
            "generate",
            "--run-mode",
            "inline",
            "--background-asset-ref",
            "bg://dummy",
            "--mlflow-tracking-uri",
            "http://mlflow.local:5000",
            "--mlflow-s3-endpoint-url",
            "http://minio.local:9000",
            "--aws-access-key-id",
            "minioadmin",
            "--aws-secret-access-key",
            "minioadmin",
            "--artifact-bucket",
            "orchestrator-artifacts",
            "--cf-access-client-id",
            "cf-client-id",
            "--cf-access-client-secret",
            "cf-client-secret",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_mode"] == "inline"
    assert payload["engine_run"]["overrides"] == [
        "adapters/artifact_store=minio",
        "adapters/tracker=mlflow_server",
        "runtime/model_runtime=cpu",
        "models/background_generator=tiny_sd_cpu",
        "models/hidden_region=tiny_torch",
        "models/inpaint=tiny_torch",
        "models/perception=tiny_torch",
        "models/fx=tiny_sd_cpu",
    ]
    assert payload["engine_run"]["runtime"]["extra_env"] == {
        "MLFLOW_TRACKING_URI": "http://mlflow.local:5000",
        "MLFLOW_S3_ENDPOINT_URL": "http://minio.local:9000",
        "AWS_ACCESS_KEY_ID": "minioadmin",
        "AWS_SECRET_ACCESS_KEY": "minioadmin",
        "ARTIFACT_BUCKET": "orchestrator-artifacts",
    }
    assert payload["env"] == {
        "CF_ACCESS_CLIENT_ID": "cf-client-id",
        "CF_ACCESS_CLIENT_SECRET": "cf-client-secret",
    }
    assert payload["engine_run"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-cpu",
    ]
    assert payload["job_name"] == "generate--generate--local-tiny-cpu"


def test_register_script_remote_profile_adds_postgres_when_metadata_url_present() -> (
    None
):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--execution-profile",
            "remote-gpu-hf",
            "--command",
            "generate",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "dev",
            "--background-asset-ref",
            "bg://dummy",
            "--metadata-db-url",
            "postgresql://user:pass@db.example/discoverex",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["overrides"] == [
        "adapters/artifact_store=minio",
        "adapters/tracker=mlflow_server",
        "adapters/metadata_store=postgres",
        "runtime/model_runtime=gpu",
        "models/background_generator=hf",
        "models/hidden_region=hf",
        "models/inpaint=hf",
        "models/perception=hf",
        "models/fx=hf",
    ]
    assert payload["engine_run"]["runtime"]["extra_env"]["METADATA_DB_URL"].startswith(
        "postgresql://"
    )
    assert payload["engine_run"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-gpu",
    ]
    assert payload["job_name"] == "generate--generate--remote-gpu-hf"


def test_register_script_generator_sdxl_gpu_profile_sets_dedicated_models() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--execution-profile",
            "generator-sdxl-gpu",
            "--command",
            "generate",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--background-prompt",
            "rainy neon alley",
            "--object-prompt",
            "hidden silver coin",
            "--final-prompt",
            "polished puzzle render",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["args"]["final_prompt"] == "polished puzzle render"
    assert payload["job_name"] == "generate--generate--generator-sdxl-gpu"
    assert payload["engine_run"]["overrides"] == [
        "adapters/artifact_store=minio",
        "adapters/tracker=mlflow_server",
        "runtime/model_runtime=gpu",
        "models/background_generator=sdxl_gpu",
        "models/hidden_region=hf",
        "models/inpaint=sdxl_gpu",
        "models/perception=hf",
        "models/fx=sdxl_gpu",
    ]


def test_register_script_allows_explicit_config_name_and_dir() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--command",
            "verify",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--scene-json",
            "/tmp/scene.json",
            "--config-name",
            "verify_prod",
            "--config-dir",
            "/srv/discoverex/conf",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["config_name"] == "verify_prod"
    assert payload["engine_run"]["config_dir"] == "/srv/discoverex/conf"
    assert payload["job_name"] == "verify--verify_prod--none"
    assert payload["engine_run"]["overrides"] == []


def test_register_script_accepts_custom_entrypoint_for_inline_mode() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--run-mode",
            "inline",
            "--entrypoint-shell-command",
            "cd /opt/engine-src && PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher",
            "--command",
            "generate",
            "--background-asset-ref",
            "bg://dummy",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_mode"] == "inline"
    assert payload["entrypoint"] == [
        "/bin/sh",
        "-lc",
        "cd /opt/engine-src && PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher",
    ]
