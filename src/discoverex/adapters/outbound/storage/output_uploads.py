from __future__ import annotations

import json
from pathlib import Path

from discoverex.settings import AppSettings
from discoverex.orchestrator_contract.artifacts import EngineArtifactManifest

from .gateway import upload_bytes
from .paths import resolve_artifact_path
from .presign import prepare_custom_links, prepare_links, put_custom_link
from .types import EngineUploadResult


def upload_outputs(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    settings: AppSettings | dict[str, object],
) -> dict[str, str]:
    links = prepare_links(
        flow_run_id=flow_run_id,
        attempt=attempt,
        entries=("stdout", "stderr", "result", "manifest"),
        settings=settings,
    )
    uploaded: dict[str, str] = {}
    for row in links:
        kind = str(row["kind"])
        object_uri = str(row["object_uri"])
        put_url = str(row["url"])
        if kind == "manifest":
            manifest_path = Path(local_paths["result"]).parent / "artifacts.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "flow_run_id": flow_run_id,
                        "attempt": attempt,
                        "artifacts": [
                            {"kind": name, "object_uri": uri}
                            for name, uri in uploaded.items()
                        ],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            upload_bytes(put_url, manifest_path.read_bytes(), settings=settings)
        else:
            upload_bytes(
                put_url,
                Path(local_paths[kind]).read_bytes(),
                settings=settings,
            )
        uploaded[kind] = object_uri
    return uploaded


def upload_engine_artifacts(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    require_manifest: bool,
    settings: AppSettings | dict[str, object],
) -> EngineUploadResult:
    manifest_path = Path(local_paths["engine_artifact_manifest"])
    artifact_dir = Path(local_paths["engine_artifact_dir"])
    if not manifest_path.exists():
        if require_manifest:
            raise RuntimeError(
                f"successful engine run must write manifest: {manifest_path}"
            )
        return EngineUploadResult(
            artifact_uris={},
            manifest_uri="",
            mlflow_tags={},
        )
    manifest = EngineArtifactManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    links = prepare_custom_links(
        flow_run_id=flow_run_id,
        attempt=attempt,
        filenames=[f"engine/{item.relative_path}" for item in manifest.artifacts],
        settings=settings,
    )
    uploaded: dict[str, str] = {}
    for item, row in zip(manifest.artifacts, links, strict=True):
        src = resolve_artifact_path(artifact_dir, item.relative_path)
        upload_bytes(str(row["url"]), src.read_bytes(), settings=settings)
        uploaded[item.logical_name] = str(row["object_uri"])
    manifest_row = put_custom_link(
        flow_run_id=flow_run_id,
        attempt=attempt,
        filename="engine-artifacts.json",
        settings=settings,
    )
    payload = {
        "schema_version": manifest.schema_version,
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "artifacts": [
            {
                "logical_name": item.logical_name,
                "relative_path": item.relative_path,
                "content_type": item.content_type,
                "mlflow_tag": item.mlflow_tag,
                "description": item.description,
                "object_uri": uploaded[item.logical_name],
            }
            for item in manifest.artifacts
        ],
    }
    upload_bytes(
        str(manifest_row["url"]),
        json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8"),
        settings=settings,
    )
    mlflow_tags = {
        str(item.mlflow_tag): uploaded[item.logical_name]
        for item in manifest.artifacts
        if item.mlflow_tag
    }
    return EngineUploadResult(
        artifact_uris=uploaded,
        manifest_uri=str(manifest_row["object_uri"]),
        mlflow_tags=mlflow_tags,
    )
