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
        == "python -m discoverex.orchestrator_contract.launcher"
    )
    assert payload["inputs"]["contract_version"] == "v2"
    assert payload["inputs"]["command"] == "generate"
    assert payload["inputs"]["args"]["background_asset_ref"] == "bg://dummy"
    assert payload["inputs"]["overrides"] == ["adapters/artifact_store=minio"]


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
    assert payload["inputs"]["contract_version"] == "v1"
    assert payload["inputs"]["command"] == "gen-verify"
