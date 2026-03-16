from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EngineCommandV1 = Literal["gen-verify", "verify-only", "replay-eval"]
EngineCommandV2 = Literal["generate", "verify", "animate"]
RuntimeMode = Literal["worker", "local", "local_debug"]
BootstrapMode = Literal["auto", "uv", "pip"]
RepoStrategy = Literal["none", "ensure", "update"]
DepsStrategy = Literal["none", "ensure", "sync"]
WorkspaceStrategy = Literal["reuse", "fresh"]


class JobRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RuntimeMode = "worker"
    bootstrap_mode: BootstrapMode = "auto"
    extras: list[str] = Field(default_factory=lambda: ["tracking", "storage"])
    extra_env: dict[str, str] = Field(default_factory=dict)
    repo_strategy: RepoStrategy = "none"
    deps_strategy: DepsStrategy = "none"
    workspace_strategy: WorkspaceStrategy = "reuse"

    @model_validator(mode="after")
    def validate_extras(self) -> "JobRuntime":
        cleaned = [item.strip() for item in self.extras if item.strip()]
        self.extras = list(dict.fromkeys(cleaned))
        if self.mode in {"local", "local_debug"}:
            self.repo_strategy = "none"
            self.deps_strategy = "none"
            self.workspace_strategy = "reuse"
        return self


class EngineRunSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"]
    command: EngineCommandV1
    config_name: str | None = None
    config_dir: str | None = None
    resolved_config: dict[str, Any] | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    overrides: list[str] = Field(default_factory=list)
    runtime: JobRuntime = Field(default_factory=JobRuntime)

    @model_validator(mode="after")
    def validate_required_args(self) -> "EngineRunSpecV1":
        required_by_command: dict[str, tuple[str, ...]] = {
            "gen-verify": (),
            "verify-only": ("scene_json",),
            "replay-eval": ("scene_jsons",),
        }
        _validate_required_args(self.command, self.args, required_by_command)
        if self.command == "gen-verify":
            _validate_generate_args(self.args)
        return self


class EngineRunSpecV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v2"]
    command: EngineCommandV2
    config_name: str | None = None
    config_dir: str | None = None
    resolved_config: dict[str, Any] | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    overrides: list[str] = Field(default_factory=list)
    runtime: JobRuntime = Field(default_factory=JobRuntime)

    @model_validator(mode="after")
    def validate_required_args(self) -> "EngineRunSpecV2":
        required_by_command: dict[str, tuple[str, ...]] = {
            "generate": (),
            "verify": ("scene_json",),
            "animate": (),
        }
        _validate_required_args(self.command, self.args, required_by_command)
        if self.command == "generate":
            _validate_generate_args(self.args)
        return self


def _validate_required_args(
    command: str,
    args: dict[str, Any],
    required_by_command: dict[str, tuple[str, ...]],
) -> None:
    missing = [key for key in required_by_command[command] if key not in args]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"missing required args for command={command}: {missing_str}")


def _validate_generate_args(args: dict[str, Any]) -> None:
    background_asset_ref = str(args.get("background_asset_ref", "")).strip()
    background_prompt = str(args.get("background_prompt", "")).strip()
    if background_asset_ref or background_prompt:
        return
    raise ValueError(
        "missing required args for command=generate: background_asset_ref or background_prompt"
    )


EngineRunSpec = EngineRunSpecV1 | EngineRunSpecV2


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_mode: Literal["repo", "inline"]
    engine: str
    repo_url: str | None = None
    ref: str | None = None
    entrypoint: list[str]
    config: str | None = None
    job_name: str | None = None
    inputs: EngineRunSpec
    env: dict[str, str] = Field(default_factory=dict)
    outputs_prefix: str | None = None

    @property
    def engine_run(self) -> EngineRunSpec:
        return self.inputs


EngineJob = EngineRunSpec
EngineJobV1 = EngineRunSpecV1
EngineJobV2 = EngineRunSpecV2
ExecutionInputs = EngineRunSpec
ExecutionInputsV1 = EngineRunSpecV1
ExecutionInputsV2 = EngineRunSpecV2
