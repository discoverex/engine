# Engine Run Contract

This document defines the engine-facing `EngineRunSpec`.

`EngineRunSpec` is sufficient to execute the engine without a worker wrapper.
Wrapper and Prefect integration may add orchestration-only fields around it, but
the engine itself only consumes this payload.

## Schema

- `contract_version: "v1" | "v2"`
- `command: str`
- `config_name: str | None`
- `config_dir: str | None`
- `args: dict[str, Any]`
- `overrides: list[str]`
- `runtime`
  - `mode: "worker" | "local_debug"`
  - `bootstrap_mode: "auto" | "uv" | "pip"`
  - `extras: list[str]`
  - `extra_env: dict[str, str]`

## Ownership

- Engine owns:
  - command/config/args/overrides resolution
  - child process runtime env derived from `runtime.extra_env`
  - CLI execution and result payload
- Wrapper owns:
  - `repo_url`, `ref`, `entrypoint`, `env`, `outputs_prefix`
  - Prefect submission, retries, and orchestration metadata
  - `resume_key`, `checkpoint_dir`

## Compatibility

- `v2` commands are `generate`, `verify`, `animate`.
- `v1` shim remains supported:
  - `gen-verify -> generate`
  - `verify-only -> verify`
  - `replay-eval -> animate`

## Local Wrapper Runs

- Direct engine execution can use this spec without Prefect.
- Wrapper-driven local tests may also pass this spec via `ORCH_JOB_INPUTS_JSON`.
- `MLFLOW_TRACKING_URI` values pointing to `localhost` or `127.0.0.1` are allowed
  without `MLFLOW_TRACKING_PROXY_URL`.
