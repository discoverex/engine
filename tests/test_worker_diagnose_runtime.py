from __future__ import annotations

from typing import Any

from infra.worker import diagnose_runtime


def test_build_report_contains_expected_sections(monkeypatch: Any) -> None:
    monkeypatch.setenv("DISCOVEREX_WORKER_RUNTIME_DIR", "/tmp/discoverex-runtime")

    report = diagnose_runtime.build_report()

    assert set(report.keys()) == {
        "python",
        "env",
        "filesystem",
        "modules",
        "imports",
    }
    assert report["env"]["DISCOVEREX_WORKER_RUNTIME_DIR"] == "/tmp/discoverex-runtime"
    assert "torch" in report["modules"]
    assert "prefect_flow" in report["imports"]


def test_module_info_reports_missing_module() -> None:
    info = diagnose_runtime._module_info("discoverex_missing_module_for_test")

    assert info["available"] is False
    assert "error" in info
