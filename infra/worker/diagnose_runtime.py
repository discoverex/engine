from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def _masked_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        return ""
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def _module_info(name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "available": True,
        "version": str(getattr(module, "__version__", "")),
        "file": str(getattr(module, "__file__", "")),
    }


def _discoverex_info() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in ("prefect_flow", "infra.prefect.flow", "discoverex"):
        payload[name] = _module_info(name)
    return payload


def _python_info() -> dict[str, Any]:
    site_packages = [path for path in sys.path if "site-packages" in path]
    return {
        "executable": sys.executable,
        "version": sys.version,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "venv_active": sys.prefix != sys.base_prefix or bool(os.environ.get("VIRTUAL_ENV")),
        "which_python": shutil.which("python") or "",
        "which_pip": shutil.which("pip") or "",
        "cwd": os.getcwd(),
        "platform": platform.platform(),
        "sys_path": list(sys.path),
        "site_packages": site_packages,
    }


def _runtime_info() -> dict[str, Any]:
    modules = {
        name: _module_info(name)
        for name in (
            "torch",
            "torchvision",
            "transformers",
            "diffusers",
            "accelerate",
            "mlflow",
            "boto3",
            "prefect",
        )
    }
    torch_info = modules["torch"]
    if torch_info.get("available"):
        try:
            import torch  # type: ignore

            modules["torch"]["cuda_available"] = bool(torch.cuda.is_available())
            modules["torch"]["cuda_device_count"] = int(torch.cuda.device_count())
            modules["torch"]["cuda_version"] = str(getattr(torch.version, "cuda", ""))
        except Exception as exc:
            modules["torch"]["cuda_probe_error"] = f"{type(exc).__name__}: {exc}"
    return modules


def _env_info() -> dict[str, Any]:
    direct_names = [
        "PREFECT_API_URL",
        "PREFECT_WORK_POOL",
        "PREFECT_WORK_QUEUE",
        "PREFECT_BATCH_WORK_QUEUE",
        "DISCOVEREX_WORKER_RUNTIME_DIR",
        "DISCOVEREX_CACHE_DIR",
        "MODEL_CACHE_DIR",
        "UV_CACHE_DIR",
        "HF_HOME",
        "PYTHONPATH",
        "UV_PROJECT_ENVIRONMENT",
        "ORCHESTRATOR_CHECKPOINT_DIR",
    ]
    secret_names = [
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "HF_TOKEN",
        "HUGGINGFACE_HUB_TOKEN",
        "HUGGINGFACE_TOKEN",
    ]
    payload = {name: os.environ.get(name, "") for name in direct_names}
    payload.update({name: _masked_env(name) for name in secret_names})
    return payload


def _filesystem_info() -> dict[str, Any]:
    app_root = Path("/app")
    runtime_root = Path(
        os.environ.get("DISCOVEREX_WORKER_RUNTIME_DIR", "/var/lib/discoverex")
    )
    repo_root = Path.cwd()
    targets = {
        "cwd": repo_root,
        "app_root": app_root,
        "src": app_root / "src",
        "infra": app_root / "infra",
        "conf": app_root / "conf",
        "prefect_flow": app_root / "prefect_flow.py",
        "runtime_root": runtime_root,
        "runtime_cache": runtime_root / "cache",
        "runtime_checkpoints": runtime_root / "checkpoints",
    }
    return {
        name: {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
        }
        for name, path in targets.items()
    }


def build_report() -> dict[str, Any]:
    return {
        "python": _python_info(),
        "env": _env_info(),
        "filesystem": _filesystem_info(),
        "modules": _runtime_info(),
        "imports": _discoverex_info(),
    }


def _print_text(report: dict[str, Any]) -> None:
    print("== Python ==")
    python = report["python"]
    print(f"executable: {python['executable']}")
    print(f"which python: {python['which_python']}")
    print(f"which pip: {python['which_pip']}")
    print(f"prefix: {python['prefix']}")
    print(f"base_prefix: {python['base_prefix']}")
    print(f"venv_active: {python['venv_active']}")
    print(f"cwd: {python['cwd']}")
    print(f"platform: {python['platform']}")
    print("site_packages:")
    for entry in python["site_packages"]:
        print(f"  - {entry}")
    print("sys_path:")
    for entry in python["sys_path"]:
        print(f"  - {entry}")

    print("\n== Environment ==")
    for key, value in report["env"].items():
        print(f"{key}: {value}")

    print("\n== Filesystem ==")
    for key, value in report["filesystem"].items():
        print(
            f"{key}: path={value['path']} exists={value['exists']} is_dir={value['is_dir']}"
        )

    print("\n== Runtime Modules ==")
    for key, value in report["modules"].items():
        details = [f"available={value.get('available', False)}"]
        if value.get("version"):
            details.append(f"version={value['version']}")
        if value.get("file"):
            details.append(f"file={value['file']}")
        if value.get("cuda_available") is not None:
            details.append(f"cuda_available={value['cuda_available']}")
        if value.get("cuda_device_count") is not None:
            details.append(f"cuda_device_count={value['cuda_device_count']}")
        if value.get("cuda_version"):
            details.append(f"cuda_version={value['cuda_version']}")
        if value.get("error"):
            details.append(f"error={value['error']}")
        if value.get("cuda_probe_error"):
            details.append(f"cuda_probe_error={value['cuda_probe_error']}")
        print(f"{key}: {' '.join(details)}")

    print("\n== Discoverex Imports ==")
    for key, value in report["imports"].items():
        details = [f"available={value.get('available', False)}"]
        if value.get("version"):
            details.append(f"version={value['version']}")
        if value.get("file"):
            details.append(f"file={value['file']}")
        if value.get("error"):
            details.append(f"error={value['error']}")
        print(f"{key}: {' '.join(details)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect remote worker runtime, imports, and dependency state."
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
