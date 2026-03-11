from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoverex.application.contracts.execution.schema import JobSpec


@dataclass(frozen=True)
class ExecutionPreparation:
    working_directory: Path
    workspace_directory: Path
    uv_cache_directory: Path
    actions: tuple[str, ...]


def prepare_execution(
    job_spec: JobSpec,
    *,
    cwd: Path | None = None,
) -> ExecutionPreparation:
    runtime = job_spec.engine_run.runtime
    base_dir = (cwd or Path.cwd()).resolve()
    uv_cache_directory = base_dir / ".cache" / "uv"
    workspace_directory = base_dir
    actions: list[str] = []

    if runtime.mode in {"local", "local_debug"}:
        return ExecutionPreparation(
            working_directory=base_dir,
            workspace_directory=base_dir,
            uv_cache_directory=uv_cache_directory,
            actions=("fast-path",),
        )

    if runtime.repo_strategy in {"ensure", "update"}:
        _require_engine_repo(base_dir)
        actions.append(f"repo:{runtime.repo_strategy}")
    if runtime.workspace_strategy == "fresh":
        workspace_directory = _ensure_workspace(base_dir, job_spec.job_name)
        actions.append("workspace:fresh")
    else:
        actions.append("workspace:reuse")
    if runtime.deps_strategy in {"ensure", "sync"}:
        uv_cache_directory.mkdir(parents=True, exist_ok=True)
        actions.append(f"deps:{runtime.deps_strategy}")

    return ExecutionPreparation(
        working_directory=base_dir,
        workspace_directory=workspace_directory,
        uv_cache_directory=uv_cache_directory,
        actions=tuple(actions or ["worker:no-op"]),
    )


def _require_engine_repo(base_dir: Path) -> None:
    required = (
        base_dir / "pyproject.toml",
        base_dir / "src" / "discoverex",
    )
    missing = [str(path.relative_to(base_dir)) for path in required if not path.exists()]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"execution preparation requires engine repo files: {missing_str}")


def _ensure_workspace(base_dir: Path, job_name: str | None) -> Path:
    workspace_root = base_dir / ".cache" / "discoverex" / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    target_name = (job_name or "job").strip() or "job"
    workspace_dir = workspace_root / target_name.replace("/", "-")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir

