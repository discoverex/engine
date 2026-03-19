from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from urllib.request import urlopen

from infra.prefect.artifacts import (
    raise_if_failed_payload,
    upload_worker_artifacts,
    write_local_artifacts,
)
from infra.prefect.runtime import ARTIFACT_DIR_ENV, ARTIFACT_MANIFEST_ENV

DEFAULT_MODEL_GROUP = "tiny_torch"
DEFAULT_BUCKET = "discoverex-e2e-artifacts"
DEFAULT_LIVE_ARTIFACT_BUCKET = "discoverex-artifacts"
DEFAULT_LIVE_MLFLOW_URI = "http://127.0.0.1:5000"
DEFAULT_LIVE_S3_ENDPOINT = "http://127.0.0.1:9000"


@dataclass(frozen=True)
class E2ERunSummary:
    scenario: str
    work_dir: str
    scene_id: str
    version_id: str
    scene_json: str
    verification_json: str
    execution_config: str
    extra: dict[str, Any]


class LiveInfraError(RuntimeError):
    pass


class _Logger:
    def info(self, _message: str, *_args: Any) -> None:
        return None


class _FakeS3ClientError(Exception):
    pass


@dataclass
class _FakeS3Store:
    buckets: dict[str, dict[str, bytes]]

    def __init__(self) -> None:
        self.buckets = {}

    def bucket(self, name: str) -> dict[str, bytes]:
        return self.buckets.setdefault(name, {})


class _FakeS3Client:
    def __init__(self, store: _FakeS3Store) -> None:
        self._store = store

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self._store.buckets:
            raise _FakeS3ClientError(Bucket)

    def create_bucket(self, *, Bucket: str) -> None:
        self._store.bucket(Bucket)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self._store.bucket(Bucket)[Key] = bytes(Body)


@contextmanager
def _patched_fake_s3_modules(store: _FakeS3Store) -> Iterator[None]:
    saved = {
        name: sys.modules.get(name)
        for name in (
            "boto3",
            "botocore",
            "botocore.client",
            "botocore.config",
            "botocore.exceptions",
        )
    }
    boto3_module = types.ModuleType("boto3")
    boto3_module.client = lambda service_name, **_: _build_fake_client(  # type: ignore[attr-defined]
        service_name, store
    )
    botocore_module = types.ModuleType("botocore")
    client_module = types.ModuleType("botocore.client")
    client_module.BaseClient = _FakeS3Client  # type: ignore[attr-defined]
    config_module = types.ModuleType("botocore.config")
    exceptions_module = types.ModuleType("botocore.exceptions")

    class Config:
        def __init__(self, **_: Any) -> None:
            return None

    config_module.Config = Config  # type: ignore[attr-defined]
    exceptions_module.ClientError = _FakeS3ClientError  # type: ignore[attr-defined]

    sys.modules["boto3"] = boto3_module
    sys.modules["botocore"] = botocore_module
    sys.modules["botocore.client"] = client_module
    sys.modules["botocore.config"] = config_module
    sys.modules["botocore.exceptions"] = exceptions_module
    try:
        yield None
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _build_fake_client(service_name: str, store: _FakeS3Store) -> _FakeS3Client:
    if service_name != "s3":
        raise RuntimeError(f"unsupported fake service_name={service_name}")
    return _FakeS3Client(store)


@contextmanager
def _patched_environ(updates: dict[str, str]) -> Iterator[None]:
    before = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield None
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass
class _StorageApiState:
    root_dir: Path

    def put(self, object_key: str, payload: bytes) -> None:
        target = self.root_dir / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    def read_json_uri(self, object_uri: str) -> Any:
        return json.loads(self._path_for_uri(object_uri).read_text(encoding="utf-8"))

    def exists_uri(self, object_uri: str) -> bool:
        return self._path_for_uri(object_uri).exists()

    def _path_for_uri(self, object_uri: str) -> Path:
        prefix = f"s3://{DEFAULT_BUCKET}/"
        if not object_uri.startswith(prefix):
            raise RuntimeError(f"unexpected object_uri={object_uri}")
        return self.root_dir / object_uri.removeprefix(prefix)


@contextmanager
def _patched_storage_uploads(state: _StorageApiState) -> Iterator[None]:
    from discoverex.orchestrator_contract.uploads import (
        engine_artifacts,
        presign,
        results,
    )

    engine_artifacts_module = cast(Any, engine_artifacts)
    presign_module = cast(Any, presign)
    results_module = cast(Any, results)
    saved_presign_http_json = presign_module.http_json
    saved_presign_storage_base_url = presign_module.storage_base_url
    saved_results_upload_bytes = results_module.upload_bytes
    saved_engine_upload_bytes = engine_artifacts_module.upload_bytes

    def fake_storage_base_url() -> str:
        return "http://storage.mock"

    def fake_http_json(method: str, url: str, payload: dict[str, Any]) -> Any:
        _ = method
        if url.endswith("/v1/presign/batch"):
            entries = payload["entries"]
            return [
                _prepare_storage_entry(
                    kind=str(entry["kind"]),
                    filename=str(entry["filename"]),
                    flow_run_id=str(entry["flow_run_id"]),
                    attempt=int(entry["attempt"]),
                )
                for entry in entries
            ]
        if url.endswith("/v1/presign/put"):
            return _prepare_storage_entry(
                kind=str(payload["kind"]),
                filename=str(payload["filename"]),
                flow_run_id=str(payload["flow_run_id"]),
                attempt=int(payload["attempt"]),
            )
        raise RuntimeError(f"unexpected fake storage url={url}")

    def fake_upload_bytes(url: str, payload: bytes) -> None:
        prefix = "memory://"
        if not url.startswith(prefix):
            raise RuntimeError(f"unexpected fake upload url={url}")
        state.put(url.removeprefix(prefix), payload)

    presign_module.http_json = fake_http_json
    presign_module.storage_base_url = fake_storage_base_url
    results_module.upload_bytes = fake_upload_bytes
    engine_artifacts_module.upload_bytes = fake_upload_bytes
    try:
        yield None
    finally:
        presign_module.http_json = saved_presign_http_json
        presign_module.storage_base_url = saved_presign_storage_base_url
        results_module.upload_bytes = saved_results_upload_bytes
        engine_artifacts_module.upload_bytes = saved_engine_upload_bytes


def _prepare_storage_entry(
    *, kind: str, filename: str, flow_run_id: str, attempt: int
) -> dict[str, str]:
    key = f"jobs/{flow_run_id}/attempt-{attempt}/{filename}"
    return {
        "kind": kind,
        "object_uri": f"s3://{DEFAULT_BUCKET}/{key}",
        "url": f"memory://{key}",
    }


def _prefect_local_env() -> dict[str, str]:
    return {
        "PREFECT_API_URL": "",
        "PREFECT_EVENTS_ENABLED": "false",
        "PREFECT_SERVER_ALLOW_EPHEMERAL_MODE": "true",
        "PREFECT_LOGGING_TO_API_ENABLED": "false",
    }


def run_tracking_artifact_e2e(
    *,
    work_dir: Path,
    model_group: str = DEFAULT_MODEL_GROUP,
) -> E2ERunSummary:
    import mlflow
    from mlflow.tracking import MlflowClient

    _require_model_runtime(model_group)
    run_dir = work_dir / "tracking-artifact"
    artifacts_root = (run_dir / "artifacts").resolve()
    tracking_uri = f"sqlite:///{(run_dir / 'mlflow.db').resolve()}"
    bucket = "tracking-artifact-e2e"

    fake_s3_store = _FakeS3Store()
    with (
        _patched_fake_s3_modules(fake_s3_store),
        _patched_environ(_prefect_local_env()),
    ):
        payload = _run_generate_payload(
            background_asset_ref="bg://engine-e2e",
            overrides=_tiny_overrides(
                model_group=model_group,
                artifacts_root=artifacts_root,
            )
            + [
                "adapters/artifact_store=minio",
                "adapters/tracker=mlflow_local",
                f"runtime.env.tracking_uri={tracking_uri}",
                f"runtime.env.artifact_bucket={bucket}",
                "runtime.env.s3_endpoint_url=http://minio.mock:9000",
            ],
        )
    raise_if_failed_payload(payload)
    scene_json = Path(str(payload["scene_json"]))
    scene_id = str(payload["scene_id"])
    version_id = str(payload["version_id"])
    metadata_dir = scene_json.parent
    verification_json = metadata_dir / "verification.json"
    prompt_bundle = metadata_dir / "prompt_bundle.json"
    execution_config = Path(str(payload["execution_config"]))
    assert scene_json.exists()
    assert verification_json.exists()
    assert prompt_bundle.exists()
    assert execution_config.exists()

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name("discoverex-core")
    if experiment is None:
        raise RuntimeError("MLflow experiment discoverex-core was not created")
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        raise RuntimeError("MLflow run was not created")
    latest_run = runs[0]

    def _artifact_paths(path: str = "") -> set[str]:
        paths: set[str] = set()
        for item in client.list_artifacts(latest_run.info.run_id, path=path):
            item_path = str(item.path)
            if getattr(item, "is_dir", False):
                paths.update(_artifact_paths(item_path))
            else:
                paths.add(item_path)
        return paths

    artifact_names = _artifact_paths()
    bucket_objects = set(fake_s3_store.bucket(bucket).keys())
    required_objects = {
        f"scenes/{scene_id}/{version_id}/metadata/scene.json",
        f"scenes/{scene_id}/{version_id}/metadata/verification.json",
        f"scenes/{scene_id}/{version_id}/metadata/prompt_bundle.json",
    }
    missing_objects = sorted(required_objects - bucket_objects)
    if missing_objects:
        raise RuntimeError(
            f"fake minio missing expected objects: {', '.join(missing_objects)}"
        )
    return E2ERunSummary(
        scenario="tracking-artifact",
        work_dir=str(run_dir),
        scene_id=scene_id,
        version_id=version_id,
        scene_json=str(scene_json),
        verification_json=str(verification_json),
        execution_config=str(execution_config),
        extra={
            "artifact_bucket": bucket,
            "bucket_objects": sorted(bucket_objects),
            "mlflow_experiment_id": experiment.experiment_id,
            "mlflow_run_id": latest_run.info.run_id,
            "mlflow_artifacts": sorted(artifact_names),
            "mlflow_params": {
                "scene_id": latest_run.data.params.get("scene_id", ""),
                "version_id": latest_run.data.params.get("version_id", ""),
            },
        },
    )


def run_worker_contract_e2e(
    *,
    work_dir: Path,
    model_group: str = DEFAULT_MODEL_GROUP,
) -> E2ERunSummary:
    _require_model_runtime(model_group)
    run_dir = work_dir / "worker-contract"
    artifact_dir = (run_dir / "engine-artifacts").resolve()
    manifest_path = artifact_dir / "engine-artifacts.json"
    storage_state = _StorageApiState(run_dir / "uploaded")
    env = {
        ARTIFACT_DIR_ENV: str(artifact_dir),
        ARTIFACT_MANIFEST_ENV: str(manifest_path),
    }
    with (
        _patched_storage_uploads(storage_state),
        _patched_environ(
            {
                **env,
                **_prefect_local_env(),
                "STORAGE_API_URL": "http://storage.mock",
            }
        ),
    ):
        payload = _run_generate_payload(
            background_asset_ref="bg://worker-e2e",
            overrides=_tiny_overrides(
                model_group=model_group,
                artifacts_root=run_dir / "ignored-artifacts-root",
            )
            + [
                "adapters/artifact_store=local",
                "adapters/tracker=mlflow_server",
            ],
            worker_runtime=True,
        )
        raise_if_failed_payload(payload)
        job_spec = {
            "engine": "discoverex",
            "run_mode": "inline",
            "job_name": "worker-contract-e2e",
        }
        local_paths = write_local_artifacts(
            env={**os.environ},
            parsed=payload,
            flow_run_id="e2e-flow",
            attempt=1,
            job_spec=job_spec,
        )
        uploaded = upload_worker_artifacts(
            flow_run_id="e2e-flow",
            attempt=1,
            local_paths=local_paths,
            require_manifest=True,
            logger=_Logger(),
        )
    scene_json = Path(str(payload["scene_json"]))
    scene_id = str(payload["scene_id"])
    version_id = str(payload["version_id"])
    verification_json = scene_json.parent / "verification.json"
    execution_config = Path(str(payload["execution_config"]))
    if not manifest_path.exists():
        raise RuntimeError("worker engine artifact manifest was not written")
    if not uploaded.get("engine_manifest_uri"):
        raise RuntimeError("worker upload did not return engine manifest uri")
    engine_manifest = storage_state.read_json_uri(str(uploaded["engine_manifest_uri"]))
    return E2ERunSummary(
        scenario="worker-contract",
        work_dir=str(run_dir),
        scene_id=scene_id,
        version_id=version_id,
        scene_json=str(scene_json),
        verification_json=str(verification_json),
        execution_config=str(execution_config),
        extra={
            "engine_manifest_path": str(manifest_path),
            "uploaded": uploaded,
            "uploaded_manifest": engine_manifest,
            "uploaded_objects": _uploaded_objects(storage_state.root_dir),
        },
    )


def run_live_services_e2e(
    *,
    work_dir: Path,
    model_group: str = DEFAULT_MODEL_GROUP,
    tracking_uri: str = DEFAULT_LIVE_MLFLOW_URI,
    s3_endpoint_url: str = DEFAULT_LIVE_S3_ENDPOINT,
    artifact_bucket: str = DEFAULT_LIVE_ARTIFACT_BUCKET,
) -> E2ERunSummary:
    import boto3
    import mlflow
    from botocore.config import Config  # type: ignore[import-untyped]
    from mlflow.tracking import MlflowClient

    _require_model_runtime(model_group)
    _require_live_service_health(
        tracking_uri=tracking_uri, s3_endpoint_url=s3_endpoint_url
    )
    run_dir = work_dir / "live-services"
    artifacts_root = (run_dir / "artifacts").resolve()
    with _patched_environ(
        {
            **_prefect_local_env(),
            "MLFLOW_TRACKING_URI": tracking_uri,
            "MLFLOW_S3_ENDPOINT_URL": s3_endpoint_url,
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            "ARTIFACT_BUCKET": artifact_bucket,
        }
    ):
        payload = _run_generate_payload(
            background_asset_ref="bg://live-services-e2e",
            overrides=_tiny_overrides(
                model_group=model_group,
                artifacts_root=artifacts_root,
            )
            + [
                "adapters/artifact_store=minio",
                "adapters/tracker=mlflow_server",
                f"runtime.env.tracking_uri={tracking_uri}",
                f"runtime.env.artifact_bucket={artifact_bucket}",
                f"runtime.env.s3_endpoint_url={s3_endpoint_url}",
                "runtime.env.aws_access_key_id=minioadmin",
                "runtime.env.aws_secret_access_key=minioadmin",
            ],
        )
    raise_if_failed_payload(payload)
    scene_json = Path(str(payload["scene_json"]))
    scene_id = str(payload["scene_id"])
    version_id = str(payload["version_id"])
    verification_json = scene_json.parent / "verification.json"
    prompt_bundle = scene_json.parent / "prompt_bundle.json"
    execution_config = Path(str(payload["execution_config"]))

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name("discoverex-core")
    if experiment is None:
        raise LiveInfraError("MLflow experiment discoverex-core not found")
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"params.scene_id = '{scene_id}'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        raise LiveInfraError(f"MLflow run for scene_id={scene_id} not found")
    latest_run = runs[0]

    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    bucket_objects = {
        item["Key"]
        for item in s3_client.list_objects_v2(Bucket=artifact_bucket).get(
            "Contents", []
        )
    }
    artifact_uri_prefix = _artifact_uri_prefix(latest_run.info.artifact_uri)
    mlflow_bucket_objects = sorted(
        key for key in bucket_objects if key.startswith(f"{artifact_uri_prefix}/")
    )
    required_objects = {
        f"scenes/{scene_id}/{version_id}/metadata/scene.json",
        f"scenes/{scene_id}/{version_id}/metadata/verification.json",
        f"scenes/{scene_id}/{version_id}/metadata/prompt_bundle.json",
    }
    missing_objects = sorted(required_objects - bucket_objects)
    if missing_objects:
        raise LiveInfraError(
            "MinIO missing expected objects: " + ", ".join(missing_objects)
        )
    return E2ERunSummary(
        scenario="live-services",
        work_dir=str(run_dir),
        scene_id=scene_id,
        version_id=version_id,
        scene_json=str(scene_json),
        verification_json=str(verification_json),
        execution_config=str(execution_config),
        extra={
            "artifact_bucket": artifact_bucket,
            "prompt_bundle": str(prompt_bundle),
            "mlflow_tracking_uri": tracking_uri,
            "mlflow_run_id": latest_run.info.run_id,
            "mlflow_artifact_uri": latest_run.info.artifact_uri,
            "mlflow_artifacts": mlflow_bucket_objects,
            "mlflow_params": {
                "scene_id": latest_run.data.params.get("scene_id", ""),
                "version_id": latest_run.data.params.get("version_id", ""),
            },
            "bucket_objects": sorted(
                key
                for key in bucket_objects
                if key.startswith(f"scenes/{scene_id}/{version_id}/")
            ),
        },
    )


def _uploaded_objects(root_dir: Path) -> list[str]:
    if not root_dir.exists():
        return []
    return sorted(
        str(path.relative_to(root_dir).as_posix())
        for path in root_dir.rglob("*")
        if path.is_file()
    )


def _artifact_uri_prefix(artifact_uri: str) -> str:
    prefix = f"s3://{DEFAULT_LIVE_ARTIFACT_BUCKET}/"
    if artifact_uri.startswith(prefix):
        return artifact_uri.removeprefix(prefix).rstrip("/")
    bucket_prefix = "s3://"
    if artifact_uri.startswith(bucket_prefix):
        return artifact_uri.split("/", 3)[-1].rstrip("/")
    raise LiveInfraError(f"unexpected artifact_uri={artifact_uri}")


def _tiny_overrides(*, model_group: str, artifacts_root: Path) -> list[str]:
    return [
        f"models/background_generator={model_group}",
        f"models/hidden_region={model_group}",
        f"models/inpaint={model_group}",
        f"models/perception={model_group}",
        f"models/fx={model_group}",
        "runtime/model_runtime=cpu",
        f"runtime.artifacts_root={artifacts_root}",
    ]


def _run_generate_payload(
    *,
    background_asset_ref: str,
    overrides: list[str],
    worker_runtime: bool = False,
) -> dict[str, str]:
    from discoverex.application.flows.common import build_scene_payload
    from discoverex.application.use_cases import run_gen_verify
    from discoverex.bootstrap import build_context
    from discoverex.config_loader import load_pipeline_config
    from discoverex.execution_snapshot import (
        build_execution_snapshot,
        write_execution_snapshot,
    )
    from discoverex.orchestrator_contract.worker_runtime import (
        normalize_pipeline_config_for_worker_runtime,
    )

    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=overrides,
    )
    if worker_runtime:
        cfg = normalize_pipeline_config_for_worker_runtime(cfg)
    execution_snapshot = build_execution_snapshot(
        command="generate",
        args={"background_asset_ref": background_asset_ref},
        config_name="generate",
        config_dir="conf",
        overrides=overrides,
        config=cfg,
    )
    execution_config_path = write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command="generate",
        snapshot=execution_snapshot,
    )
    context = build_context(
        config=cfg,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_config_path,
    )
    scene = run_gen_verify(
        background_asset_ref=background_asset_ref,
        context=context,
    )
    payload = build_scene_payload(
        cast(Any, scene),
        str(cfg.runtime.artifacts_root),
        str(execution_config_path),
    )
    return payload


def _require_model_runtime(model_group: str) -> None:
    if model_group == "tiny_hf":
        __import__("transformers")
    __import__("torch")


def ensure_live_infra(
    *,
    compose_file: Path | None = None,
    services: tuple[str, ...] = ("postgres", "minio", "mlflow"),
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise LiveInfraError("docker is required for --ensure-live-infra")
    target_compose = compose_file or Path("infra/docker-compose.yml").resolve()
    cmd = [
        docker,
        "compose",
        "-f",
        str(target_compose),
        "up",
        "-d",
        *services,
    ]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise LiveInfraError("docker compose up failed")
    _require_live_service_health(
        tracking_uri=DEFAULT_LIVE_MLFLOW_URI,
        s3_endpoint_url=DEFAULT_LIVE_S3_ENDPOINT,
    )


def _require_live_service_health(*, tracking_uri: str, s3_endpoint_url: str) -> None:
    _wait_for_http_ok(f"{tracking_uri.rstrip('/')}/health")
    _wait_for_http_ok(f"{s3_endpoint_url.rstrip('/')}/minio/health/live")


def _wait_for_http_ok(url: str, retries: int = 30) -> None:
    last_error = ""
    for _ in range(retries):
        try:
            with urlopen(url, timeout=3) as response:
                if 200 <= getattr(response, "status", 200) < 500:
                    return
        except Exception as exc:
            last_error = str(exc)
        import time

        time.sleep(1)
    raise LiveInfraError(f"service did not become ready: {url} ({last_error})")


def _summary_to_dict(summary: E2ERunSummary) -> dict[str, Any]:
    return {
        "scenario": summary.scenario,
        "work_dir": summary.work_dir,
        "scene_id": summary.scene_id,
        "version_id": summary.version_id,
        "scene_json": summary.scene_json,
        "verification_json": summary.verification_json,
        "execution_config": summary.execution_config,
        "extra": summary.extra,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run local E2E verification for engine tracking/artifact and "
            "worker-contract flows."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=("tracking-artifact", "worker-contract", "live-services", "all"),
        default="all",
    )
    parser.add_argument("--model-group", default=DEFAULT_MODEL_GROUP)
    parser.add_argument("--work-dir", default="")
    parser.add_argument(
        "--ensure-live-infra",
        action="store_true",
        help="Start docker compose services for the live-services scenario.",
    )
    args = parser.parse_args(argv)

    if args.ensure_live_infra:
        ensure_live_infra()

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        summaries = _run_requested_scenarios(
            scenario=args.scenario,
            model_group=args.model_group,
            work_dir=work_dir,
        )
        print(json.dumps(summaries, ensure_ascii=True, indent=2))
        return 0

    with TemporaryDirectory(prefix="discoverex-engine-e2e-") as temp_dir:
        summaries = _run_requested_scenarios(
            scenario=args.scenario,
            model_group=args.model_group,
            work_dir=Path(temp_dir).resolve(),
        )
        print(json.dumps(summaries, ensure_ascii=True, indent=2))
    return 0


def _run_requested_scenarios(
    *, scenario: str, model_group: str, work_dir: Path
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    if scenario in {"tracking-artifact", "all"}:
        summaries["tracking-artifact"] = _summary_to_dict(
            run_tracking_artifact_e2e(
                work_dir=work_dir,
                model_group=model_group,
            )
        )
    if scenario in {"worker-contract", "all"}:
        summaries["worker-contract"] = _summary_to_dict(
            run_worker_contract_e2e(
                work_dir=work_dir,
                model_group=model_group,
            )
        )
    if scenario in {"live-services", "all"}:
        summaries["live-services"] = _summary_to_dict(
            run_live_services_e2e(
                work_dir=work_dir,
                model_group=model_group,
            )
        )
    return summaries


if __name__ == "__main__":
    raise SystemExit(main())
