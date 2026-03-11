from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "register"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

register_job = importlib.import_module("register_orchestrator_job")


class _FakeResponse:
    def __init__(self, body: str, content_type: str = "text/html") -> None:
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, tb)

    def read(self) -> bytes:
        return self._body


def test_http_json_reports_non_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        register_job.request,
        "urlopen",
        lambda *_args, **_kwargs: _FakeResponse("<html>redirect</html>"),
    )

    with pytest.raises(SystemExit, match="returned non-JSON response"):
        register_job._http_json("POST", "https://prefect.example/api", "deployments/filter")
