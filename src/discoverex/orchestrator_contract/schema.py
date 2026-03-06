from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EngineCommand = Literal["gen-verify", "verify-only", "replay-eval"]
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


class EngineJobV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"]
    command: EngineCommand
    args: dict[str, Any] = Field(default_factory=dict)
    overrides: list[str] = Field(default_factory=list)
    runtime: JobRuntime = Field(default_factory=JobRuntime)

    @model_validator(mode="after")
    def validate_required_args(self) -> "EngineJobV1":
        required_by_command: dict[str, tuple[str, ...]] = {
            "gen-verify": ("background_asset_ref",),
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
        return self


class OrchestratorInputsV1(EngineJobV1):
    """Typed payload expected from ORCH_JOB_INPUTS_JSON."""
