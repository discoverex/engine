from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EngineCommandV1 = Literal["gen-verify", "verify-only", "replay-eval"]
EngineCommandV2 = Literal["generate", "verify", "animate"]
RuntimeMode = Literal["worker", "local_debug"]
BootstrapMode = Literal["auto", "uv", "pip"]


class JobRuntime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RuntimeMode = "worker"
    bootstrap_mode: BootstrapMode = "auto"
    extras: list[str] = Field(default_factory=lambda: ["tracking", "storage"])
    extra_env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_extras(self) -> "JobRuntime":
        cleaned = [item.strip() for item in self.extras if item.strip()]
        self.extras = list(dict.fromkeys(cleaned))
        return self


class EngineRunSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"]
    command: EngineCommandV1
    config_name: str | None = None
    config_dir: str | None = None
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
        required = required_by_command[self.command]
        missing = [key for key in required if key not in self.args]
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(
                f"missing required args for command={self.command}: {missing_str}"
            )
        if self.command == "gen-verify":
            _validate_generate_args(self.args)
        return self


class EngineRunSpecV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v2"]
    command: EngineCommandV2
    config_name: str | None = None
    config_dir: str | None = None
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
        required = required_by_command[self.command]
        missing = [key for key in required if key not in self.args]
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(
                f"missing required args for command={self.command}: {missing_str}"
            )
        if self.command == "generate":
            _validate_generate_args(self.args)
        return self


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
    engine_run: EngineRunSpec
    env: dict[str, str] = Field(default_factory=dict)
    outputs_prefix: str | None = None


EngineJob = EngineRunSpec
EngineJobV1 = EngineRunSpecV1
EngineJobV2 = EngineRunSpecV2
OrchestratorInputs = EngineRunSpec
OrchestratorInputsV1 = EngineRunSpecV1
OrchestratorInputsV2 = EngineRunSpecV2
