# Engine Run Contract

This document defines the engine-side execution payload consumed by the runtime when `discoverex` is run directly or through Prefect.

## 1. Contract Purpose

`EngineRunSpec` is the engine-facing payload that describes:

- which command to run
- which Hydra config to load
- which command arguments to pass
- which runtime mode and extras to use

The stable public surface is the command plus the `EngineRunSpec` shape. Internal handler names remain implementation details.

## 2. Stable Commands

Public engine commands:

- `generate`
- `verify`
- `animate`

Direct CLI-only command:

- `validate`

Compatibility commands retained for migration:

- `gen-verify` -> `generate`
- `verify-only` -> `verify`
- `replay-eval` -> `animate`

## 3. Payload Shape

`EngineRunSpec` contains:

- `contract_version`
- `command`
- `config_name`
- `config_dir`
- `args`
- `overrides`
- `runtime`

`runtime` contains:

- `mode`
- `bootstrap_mode`
- `extras`
- `extra_env`

In practice, direct CLI runs build this payload inline from [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py), and Prefect runs obtain it from `job_spec_json`.

## 4. Engine Responsibilities

The engine is responsible for:

- interpreting `command`, `args`, and Hydra overrides
- building application context from config
- running the requested pipeline
- emitting structured result payloads
- writing engine-owned durable artifacts only through the worker artifact contract when applicable

The engine is not responsible for:

- Prefect deployment creation
- worker scheduling
- object-store presign handling
- direct artifact upload orchestration
- MLflow post-upload artifact URI tagging

## 5. Runtime Inputs Used By The Engine

When launched by worker/Prefect runtime, the engine may consume:

- `MLFLOW_TRACKING_URI`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `ORCH_JOB_INPUTS_JSON`

The engine should use `MLFLOW_TRACKING_URI` as provided and avoid assuming direct storage credentials.

## 6. Internal Flow Mapping

Current internal flow layer:

- engine entry flow: `discoverex-engine-entry-pipeline`
- generate flow: `discoverex-generate-pipeline`
- verify flow: `discoverex-verify-pipeline`
- variant-pack flow: `discoverex-generate-inpaint-variant-pack`

Current compatibility and internal handlers include:

- `generate_v1_compat`
- `generate_v2_compat`
- `generate_verify_v2`
- `generate_object_only`
- `generate_single_object_debug`
- `generate_inpaint_variant_pack`
- `verify_v1_compat`
- `animate_replay_eval`
- `animate_stub`

These names are useful for debugging, but they are not the primary external contract.

## 7. Current Caveat

`animate` remains part of the public contract, but current implementation is not yet a fully realized production animation pipeline.
