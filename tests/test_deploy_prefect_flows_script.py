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
    created: list[tuple[str, str, str | None]] = []

    class _FakeDeployment:
        def __init__(
            self, flow_name: str, deployment_name: str, work_queue_name: str | None
        ) -> None:
            self.flow_name = flow_name
            self.deployment_name = deployment_name
            self.work_queue_name = work_queue_name

        def apply(self, work_pool_name: str) -> str:
            created.append((self.deployment_name, work_pool_name, self.work_queue_name))
            return f"id:{self.flow_name}:{self.deployment_name}"

    class _FakeFlow:
        def __init__(self, flow_name: str) -> None:
            self.flow_name = flow_name

        def to_deployment(
            self,
            *,
            name: str,
            version: str | None = None,
            work_pool_name: str,
            work_queue_name: str | None = None,
        ) -> _FakeDeployment:
            created.append((f"to:{name}", version, work_pool_name, work_queue_name))
            return _FakeDeployment(self.flow_name, name, work_queue_name)

    monkeypatch.setattr(
        deploy_flows,
        "_load_registration_flow",
        lambda **_kwargs: _FakeFlow("disoverex-engine-flow"),
    )
    monkeypatch.setattr(
        deploy_flows, "_to_runner_deployment", lambda deployment: deployment
    )

    output = deploy_flows._apply_deployments(
        work_pool_name="gpu-pool",
        flow_source="/app",
        flow_entrypoint="prefect_flow.py:run_job_flow",
        flow_ref="dev",
        deployment_version="20260312120000",
        primary_name="discoverex-engine-job",
        primary_queue="gpu-fixed",
        register_colab=True,
        colab_name="discoverex-engine-job-colab",
        colab_queue="gpu-colab",
        register_compat_aliases=True,
        compat_fixed_name="engine-job",
        compat_fixed_queue="gpu-fixed",
        compat_colab_name="engine-job-colab",
        compat_colab_queue="gpu-colab",
    )

    assert output == {
        "discoverex-engine-job": "id:disoverex-engine-flow:discoverex-engine-job",
        "discoverex-engine-job-colab": "id:disoverex-engine-flow:discoverex-engine-job-colab",
        "engine-job": "id:disoverex-engine-flow:engine-job",
        "engine-job-colab": "id:disoverex-engine-flow:engine-job-colab",
    }
    assert (
        "to:discoverex-engine-job",
        "20260312120000",
        "gpu-pool",
        "gpu-fixed",
    ) in created
    assert (
        "to:discoverex-engine-job-colab",
        "20260312120000",
        "gpu-pool",
        "gpu-colab",
    ) in created


def test_apply_deployments_registers_primary_only_by_default(
    monkeypatch: Any,
) -> None:
    created: list[tuple[str, str, str | None]] = []

    class _FakeDeployment:
        def __init__(
            self, flow_name: str, deployment_name: str, work_queue_name: str | None
        ) -> None:
            self.flow_name = flow_name
            self.deployment_name = deployment_name
            self.work_queue_name = work_queue_name

        def apply(self, work_pool_name: str) -> str:
            created.append((self.deployment_name, work_pool_name, self.work_queue_name))
            return f"id:{self.flow_name}:{self.deployment_name}"

    class _FakeFlow:
        def __init__(self, flow_name: str) -> None:
            self.flow_name = flow_name

        def to_deployment(
            self,
            *,
            name: str,
            version: str | None = None,
            work_pool_name: str,
            work_queue_name: str | None = None,
        ) -> _FakeDeployment:
            created.append((f"to:{name}", version, work_pool_name, work_queue_name))
            return _FakeDeployment(self.flow_name, name, work_queue_name)

    monkeypatch.setattr(
        deploy_flows,
        "_load_registration_flow",
        lambda **_kwargs: _FakeFlow("disoverex-engine-flow"),
    )
    monkeypatch.setattr(
        deploy_flows, "_to_runner_deployment", lambda deployment: deployment
    )

    output = deploy_flows._apply_deployments(
        work_pool_name="gpu-pool",
        flow_source="/app",
        flow_entrypoint="prefect_flow.py:run_job_flow",
        flow_ref="dev",
        deployment_version="20260312120000",
        primary_name="discoverex-engine-job",
        primary_queue="gpu-fixed",
        register_colab=False,
        colab_name="discoverex-engine-job-colab",
        colab_queue="gpu-colab",
        register_compat_aliases=False,
        compat_fixed_name="engine-job",
        compat_fixed_queue="gpu-fixed",
        compat_colab_name="engine-job-colab",
        compat_colab_queue="gpu-colab",
    )

    assert output == {
        "discoverex-engine-job": "id:disoverex-engine-flow:discoverex-engine-job",
    }
    assert created == [
        ("to:discoverex-engine-job", "20260312120000", "gpu-pool", "gpu-fixed"),
        ("discoverex-engine-job", "gpu-pool", "gpu-fixed"),
    ]


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
        lambda **_kwargs: {"discoverex-engine-job": "dep-123"},
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
    assert '"discoverex-engine-job": "dep-123"' in out
    assert (
        captured["updates"][deploy_flows.PREFECT_API_URL]
        == "https://prefect.example/api"
    )
    assert (
        "User-Agent" in captured["updates"][deploy_flows.PREFECT_CLIENT_CUSTOM_HEADERS]
    )


def test_build_parser_marks_script_as_compatibility_helper() -> None:
    parser = deploy_flows._build_parser()
    assert "Compatibility helper" in parser.description
    assert parser.parse_args([]).primary_name == "discoverex-engine-job"
    assert parser.parse_args([]).primary_queue == "gpu-fixed"
    assert parser.parse_args([]).flow_source == "/app"
    assert parser.parse_args([]).flow_ref == "dev"
    assert parser.parse_args([]).deployment_version
