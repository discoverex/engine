from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MODULE = "infra.ops.register_orchestrator_job"
BUILD_MODULE = "infra.ops.build_job_spec"


def test_register_script_dry_run_builds_worker_job_spec() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--dry-run",
            "--command",
            "generate",
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
    assert payload["run_mode"] == "inline"
    assert payload["repo_url"] is None
    assert payload["ref"] is None
    assert payload["entrypoint"] == ["prefect_flow.py:run_generate_job_flow"]
    assert payload["inputs"]["contract_version"] == "v2"
    assert payload["inputs"]["command"] == "generate"
    assert payload["inputs"]["config_name"] == "generate"
    assert payload["inputs"]["config_dir"] == "conf"
    assert payload["inputs"]["args"]["background_asset_ref"] == "bg://dummy"
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
    ]
    assert payload["job_name"] == "generate--generate--none"


def test_build_job_spec_script_writes_job_spec_file_under_register_dir(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "job_specs" / "generate--generate--none.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            BUILD_MODULE,
            "--output-file",
            str(output_path),
            "--command",
            "generate",
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
    assert Path(proc.stdout.strip()) == output_path
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["inputs"]["command"] == "generate"
    assert payload["job_name"] == "generate--generate--none"


def test_register_script_requires_command_specific_args() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
            "-m",
            MODULE,
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
    assert payload["inputs"]["args"]["background_prompt"] == "misty mountain lake"
    assert payload["inputs"]["args"]["object_prompt"] == "small hidden red lantern"
    assert payload["inputs"]["config_name"] == "generate"


def test_register_script_accepts_v1_command_when_version_is_v1() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
    assert payload["inputs"]["contract_version"] == "v1"
    assert payload["inputs"]["command"] == "gen-verify"
    assert payload["inputs"]["config_name"] == "gen_verify"


def test_register_script_local_tiny_profile_adds_worker_overrides_and_env() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
        "runtime/model_runtime=cpu",
        "runtime.width=256",
        "runtime.height=256",
        "models/background_generator=tiny_sd_cpu",
        "models/hidden_region=tiny_torch",
        "models/inpaint=tiny_torch",
        "models/perception=tiny_torch",
        "models/fx=tiny_sd_cpu",
    ]
    assert payload["inputs"]["runtime"]["extra_env"] == {}
    assert payload["env"] == {
        "CF_ACCESS_CLIENT_ID": "cf-client-id",
        "CF_ACCESS_CLIENT_SECRET": "cf-client-secret",
    }
    assert payload["inputs"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-cpu",
    ]
    assert payload["job_name"] == "generate--generate--local-tiny-cpu"


def test_register_script_remote_profile_keeps_engine_storage_local_when_metadata_url_present() -> (
    None
):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
        "runtime/model_runtime=gpu",
        "models/background_generator=hf",
        "models/hidden_region=hf",
        "models/inpaint=hf",
        "models/perception=hf",
        "models/fx=hf",
    ]
    assert payload["inputs"]["runtime"]["extra_env"] == {}
    assert payload["inputs"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-gpu",
    ]
    assert payload["job_name"] == "generate--generate--remote-gpu-hf"


def test_register_script_rejects_worker_minio_artifact_store_override() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--dry-run",
            "--command",
            "generate",
            "--background-asset-ref",
            "bg://dummy",
            "-o",
            "adapters/artifact_store=minio",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "worker runtime requires adapters/artifact_store=local" in proc.stderr


def test_register_script_generator_sdxl_gpu_profile_sets_dedicated_models() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
    assert payload["inputs"]["args"]["final_prompt"] == "polished puzzle render"
    assert payload["job_name"] == "generate--generate--generator-sdxl-gpu"
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
        "runtime/model_runtime=gpu",
        "runtime.width=512",
        "runtime.height=512",
        "models/background_generator=sdxl_gpu",
        "models/hidden_region=hf",
        "models/inpaint=sdxl_gpu",
        "models/perception=hf",
        "models/fx=copy_image",
    ]
    assert payload["inputs"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-gpu",
    ]


def test_register_script_generator_pixart_gpu_profile_sets_dedicated_models() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--dry-run",
            "--execution-profile",
            "generator-pixart-gpu",
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
    assert payload["inputs"]["args"]["final_prompt"] == "polished puzzle render"
    assert payload["job_name"] == "generate--generate--generator-pixart-gpu"
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
        "profile=generator_pixart_gpu_v2_8gb",
        "runtime/model_runtime=gpu",
        "flows/generate=v2",
        "runtime.width=1024",
        "runtime.height=1024",
        "models/background_generator=pixart_sigma_8gb",
        "models/object_generator=layerdiffuse",
        "models/hidden_region=hf",
        "models/inpaint=sdxl_gpu_similarity_v2",
        "models/perception=hf",
        "models/fx=copy_image",
        "runtime.model_runtime.offload_mode=sequential",
    ]
    assert payload["inputs"]["runtime"]["extras"] == [
        "tracking",
        "storage",
        "ml-gpu",
    ]


def test_register_script_allows_explicit_config_name_and_dir() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
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
    assert payload["inputs"]["config_name"] == "verify_prod"
    assert payload["inputs"]["config_dir"] == "/srv/discoverex/conf"
    assert payload["job_name"] == "verify--verify_prod--none"
    assert payload["inputs"]["overrides"] == [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
    ]


def test_register_script_sets_prefect_flow_entrypoint_for_inline_mode() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--dry-run",
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
    assert payload["entrypoint"] == ["prefect_flow.py:run_generate_job_flow"]
