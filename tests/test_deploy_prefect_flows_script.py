from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "infra" / "register"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

deploy_flows = importlib.import_module("deploy_prefect_flows")


def test_apply_deployments_registers_expected_names(
    monkeypatch: Any,
) -> None:
    created: list[tuple[str, str]] = []

    class _FakeDeployment:
        def __init__(self, flow_name: str, deployment_name: str) -> None:
            self.flow_name = flow_name
            self.deployment_name = deployment_name

        def apply(self, work_pool_name: str) -> str:
            created.append((self.deployment_name, work_pool_name))
            return f"id:{self.flow_name}:{self.deployment_name}"

    class _FakeFlow:
        def __init__(self, flow_name: str) -> None:
            self.flow_name = flow_name

        def to_deployment(self, *, name: str, work_pool_name: str) -> _FakeDeployment:
            created.append((f"to:{name}", work_pool_name))
            return _FakeDeployment(self.flow_name, name)

    monkeypatch.setattr(deploy_flows, "run_engine_job_flow", _FakeFlow("run-engine-job"))
    monkeypatch.setattr(deploy_flows, "_to_runner_deployment", lambda deployment: deployment)

    output = deploy_flows._apply_deployments("local-process")

    assert output == {
        "run-engine-job": "id:run-engine-job:run-engine-job",
    }
    assert ("to:run-engine-job", "local-process") in created


def test_main_sets_prefect_headers(monkeypatch: Any, capsys: Any) -> None:
    captured: dict[str, Any] = {}

    @contextmanager
    def _fake_temporary_settings(*, updates: dict[object, object]) -> Any:
        captured["updates"] = updates
        yield None

    monkeypatch.setattr(
        deploy_flows,
        "temporary_settings",
        _fake_temporary_settings,
    )
    monkeypatch.setattr(
        deploy_flows,
        "_apply_deployments",
        lambda *_args: {"run-engine-job": "dep-123"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_prefect_flows.py",
            "--prefect-api-url",
            "https://prefect.example/api",
        ],
    )

    code = deploy_flows.main()
    out = capsys.readouterr().out

    assert code == 0
    assert '"run-engine-job": "dep-123"' in out
    assert captured["updates"][deploy_flows.PREFECT_API_URL] == "https://prefect.example/api"
    assert "User-Agent" in captured["updates"][deploy_flows.PREFECT_CLIENT_CUSTOM_HEADERS]
