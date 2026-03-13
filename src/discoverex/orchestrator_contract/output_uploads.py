from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoverex.orchestrator_contract.artifacts import EngineArtifactManifest

from .storage_http import http_json, storage_base_url, upload_bytes


@dataclass(frozen=True)
class EngineUploadResult:
    artifact_uris: dict[str, str]
    manifest_uri: str

def upload_outputs(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
) -> dict[str, str]:
    links = _prepare_links(flow_run_id=flow_run_id, attempt=attempt, entries=("stdout", "stderr", "result", "manifest"))
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
            upload_bytes(put_url, manifest_path.read_bytes())
        else:
            upload_bytes(put_url, Path(local_paths[kind]).read_bytes())
        uploaded[kind] = object_uri
    return uploaded


def upload_engine_artifacts(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    require_manifest: bool,
) -> EngineUploadResult:
    manifest_path = Path(local_paths["engine_artifact_manifest"])
    artifact_dir = Path(local_paths["engine_artifact_dir"])
    if not manifest_path.exists():
        if require_manifest:
            raise RuntimeError(
                f"successful engine run must write manifest: {manifest_path}"
            )
        return EngineUploadResult(artifact_uris={}, manifest_uri="")
    manifest = EngineArtifactManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    links = _prepare_custom_links(
        flow_run_id=flow_run_id,
        attempt=attempt,
        filenames=[f"engine/{item.relative_path}" for item in manifest.artifacts],
    )
    uploaded: dict[str, str] = {}
    for item, row in zip(manifest.artifacts, links, strict=True):
        src = _resolve_artifact_path(artifact_dir, item.relative_path)
        upload_bytes(str(row["url"]), src.read_bytes())
        uploaded[item.logical_name] = str(row["object_uri"])
    manifest_row = _put_custom_link(flow_run_id=flow_run_id, attempt=attempt, filename="engine-artifacts.json")
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
    )
    return EngineUploadResult(artifact_uris=uploaded, manifest_uri=str(manifest_row["object_uri"]))


def _prepare_links(
    *,
    flow_run_id: str,
    attempt: int,
    entries: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = http_json(
        "POST",
        f"{storage_base_url()}/v1/presign/batch",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": kind,
                    "filename": _output_filename(kind),
                }
                for kind in entries
            ],
        },
    )
    if not isinstance(rows, list):
        raise RuntimeError("unexpected storage API batch response")
    return rows


def _prepare_custom_links(
    *,
    flow_run_id: str,
    attempt: int,
    filenames: list[str],
) -> list[dict[str, Any]]:
    rows = http_json(
        "POST",
        f"{storage_base_url()}/v1/presign/batch",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": "custom",
                    "filename": filename,
                }
                for filename in filenames
            ],
        },
    )
    if not isinstance(rows, list):
        raise RuntimeError("unexpected storage API custom batch response")
    return rows


def _put_custom_link(
    *,
    flow_run_id: str,
    attempt: int,
    filename: str,
) -> dict[str, Any]:
    row = http_json(
        "POST",
        f"{storage_base_url()}/v1/presign/put",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "custom",
            "filename": filename,
        },
    )
    if not isinstance(row, dict):
        raise RuntimeError("unexpected storage API put response")
    return row


def _resolve_artifact_path(artifact_dir: Path, relative_path: str) -> Path:
    resolved = (artifact_dir / relative_path).resolve()
    try:
        resolved.relative_to(artifact_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(f"engine artifact escapes artifact root: {relative_path}") from exc
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f"engine artifact file not found: {relative_path}")
    return resolved


def _output_filename(kind: str) -> str:
    if kind in {"stdout", "stderr"}:
        return f"{kind}.log"
    if kind == "manifest":
        return "artifacts.json"
    return f"{kind}.json"
