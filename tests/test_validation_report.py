from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from discoverex.adapters.outbound.models.pipeline_memory import (
    configure_diffusers_pipeline,
)
from infra.prefect.dispatch import dispatch_engine_job

# --- 1. VRAM Configuration Test ---

class _FakePipe:
    offload_mode: str | None
    sent_to_device: str | None

    def __init__(self) -> None:
        self.offload_mode = None
        self.sent_to_device = None

    def enable_model_cpu_offload(self) -> None:
        self.offload_mode = "model"

    def enable_sequential_cpu_offload(self) -> None:
        self.offload_mode = "sequential"

    def to(self, device: str) -> "_FakePipe":
        self.sent_to_device = device
        return self


def test_vram_config_sequential_offload() -> None:
    """Verify that offload_mode='sequential' triggers the correct pipeline method."""
    pipe = _FakePipe()
    handle = SimpleNamespace(device="cuda", dtype="float16")

    # Act
    configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode="sequential",
    )

    # Assert
    assert pipe.offload_mode == "sequential"
    assert pipe.sent_to_device is None  # Should not be sent to device if offloaded


# --- 2. Logging & Dispatch Error Test ---

def test_dispatch_engine_job_captures_logs_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify that subprocess failure logs are captured and raised in the exception."""
    
    # 1. Mock subprocess.Popen
    class MockPopen:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.returncode = 1
            # Mock stdout/stderr streams
            import io
            self.stdout = io.StringIO("some stdout content\n")
            self.stderr = io.StringIO("CRITICAL ERROR: Out of memory\n")

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 1
            return 1

        def poll(self) -> int | None:
            return 1

    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    
    # 2. Mock Prefect Logger (avoid context errors)
    monkeypatch.setattr("infra.prefect.dispatch.get_run_logger", lambda: MagicMock())
    
    # 3. Mock python bin check
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").touch()

    # Act & Assert
    with pytest.raises(RuntimeError) as exc_info:
        dispatch_engine_job(
            payload={"some": "payload"},
            cwd=tmp_path,
            env={"TEST": "env"},
        )

    error_msg = str(exc_info.value)
    assert "engine subprocess failed" in error_msg
    assert "exit_code: 1" in error_msg
    assert "reason: CRITICAL ERROR: Out of memory" in error_msg
