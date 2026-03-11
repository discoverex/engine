from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "register" / "register_prefect_job.py"


def test_prefect_wrapper_dry_run_defaults_to_remote_worker_profile() -> None:
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
            "feat/real-job",
            "--background-asset-ref",
            "bg://real-asset",
            "--mlflow-tracking-uri",
            "https://mlflow.example.com",
            "--mlflow-s3-endpoint-url",
            "http://minio.internal:9000",
            "--aws-access-key-id",
            "minio-user",
            "--aws-secret-access-key",
            "minio-secret",
            "--artifact-bucket",
            "orchestrator-artifacts",
            "--cf-access-client-id",
            "cf-id",
            "--cf-access-client-secret",
            "cf-secret",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["run_mode"] == "repo"
    assert payload["repo_url"] == "https://github.com/example/engine.git"
    assert payload["ref"] == "feat/real-job"
    assert payload["job_name"] == "generate--generate--generator-sdxl-gpu"
    assert payload["engine_run"]["runtime"]["extra_env"]["MLFLOW_TRACKING_URI"] == (
        "https://mlflow.example.com"
    )
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
    assert payload["env"] == {
        "CF_ACCESS_CLIENT_ID": "cf-id",
        "CF_ACCESS_CLIENT_SECRET": "cf-secret",
    }


def test_prefect_wrapper_allows_local_tiny_profile_override() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--execution-profile",
            "local-tiny-cpu",
            "--run-mode",
            "inline",
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
    assert payload["engine_run"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-cpu",
    ]
    assert payload["job_name"] == "generate--generate--local-tiny-cpu"
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


def test_prefect_wrapper_forwards_prompt_args() -> None:
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
            "feat/real-job",
            "--background-prompt",
            "stormy harbor at dusk",
            "--background-negative-prompt",
            "low quality",
            "--object-prompt",
            "hidden golden compass",
            "--object-negative-prompt",
            "blurry",
            "--final-prompt",
            "playable polished render",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["args"]["background_prompt"] == "stormy harbor at dusk"
    assert payload["engine_run"]["args"]["background_negative_prompt"] == "low quality"
    assert payload["engine_run"]["args"]["object_prompt"] == "hidden golden compass"
    assert payload["engine_run"]["args"]["object_negative_prompt"] == "blurry"
    assert payload["engine_run"]["args"]["final_prompt"] == "playable polished render"


def test_prefect_wrapper_forwards_config_selection() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--command",
            "verify",
            "--scene-json",
            "/tmp/scene.json",
            "--config-name",
            "verify_prod",
            "--config-dir",
            "/srv/conf",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["engine_run"]["config_name"] == "verify_prod"
    assert payload["engine_run"]["config_dir"] == "/srv/conf"
    assert payload["job_name"] == "verify--verify_prod--generator-sdxl-gpu"
