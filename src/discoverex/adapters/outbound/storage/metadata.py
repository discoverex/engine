from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from discoverex.domain.scene import Scene


class LocalMetadataStoreAdapter:
    def __init__(
        self,
        artifacts_root: str = "artifacts",
        metadata_index_path: str | None = None,
        **_: str,
    ) -> None:
        index = metadata_index_path or f"{artifacts_root}/metadata_index.json"
        self.index_path = Path(index)

    def _load(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        return cast(
            list[dict[str, Any]],
            json.loads(self.index_path.read_text(encoding="utf-8")),
        )

    def _dump(self, rows: list[dict[str, Any]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def upsert_scene_metadata(self, scene: Scene) -> None:
        rows = self._load()
        key = (scene.meta.scene_id, scene.meta.version_id)
        payload = _scene_metadata_payload(scene)
        updated = False
        for idx, row in enumerate(rows):
            if (row.get("scene_id"), row.get("version_id")) == key:
                rows[idx] = payload
                updated = True
                break
        if not updated:
            rows.append(payload)
        self._dump(rows)


class PostgresMetadataStoreAdapter:
    def __init__(self, metadata_db_url: str = "", **_: str) -> None:
        try:
            from sqlalchemy import create_engine, text  # type: ignore
            from sqlalchemy.engine import Engine  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "sqlalchemy dependency is required for PostgresMetadataStoreAdapter. "
                "Install with `uv sync --extra storage`."
            ) from exc

        if not metadata_db_url:
            raise ValueError(
                "metadata_db_url is required for PostgresMetadataStoreAdapter"
            )
        self._text = text
        self.engine: Engine = create_engine(metadata_db_url, future=True)
        self._ensure_table()

    def _ensure_table(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS scene_metadata (
          scene_id TEXT NOT NULL,
          version_id TEXT NOT NULL,
          status TEXT NOT NULL,
          scores JSONB NOT NULL,
          failure_reason TEXT NOT NULL,
          timestamps JSONB NOT NULL,
          PRIMARY KEY (scene_id, version_id)
        )
        """
        with self.engine.begin() as conn:
            conn.execute(self._text(ddl))

    def upsert_scene_metadata(self, scene: Scene) -> None:
        payload = _scene_metadata_payload(scene)
        stmt = self._text(
            """
            INSERT INTO scene_metadata (scene_id, version_id, status, scores, failure_reason, timestamps)
            VALUES (:scene_id, :version_id, :status, CAST(:scores AS JSONB), :failure_reason, CAST(:timestamps AS JSONB))
            ON CONFLICT (scene_id, version_id)
            DO UPDATE SET
              status = EXCLUDED.status,
              scores = EXCLUDED.scores,
              failure_reason = EXCLUDED.failure_reason,
              timestamps = EXCLUDED.timestamps
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "scene_id": payload["scene_id"],
                    "version_id": payload["version_id"],
                    "status": payload["status"],
                    "scores": json.dumps(payload["scores"]),
                    "failure_reason": payload["failure_reason"],
                    "timestamps": json.dumps(payload["timestamps"]),
                },
            )


def _scene_metadata_payload(scene: Scene) -> dict[str, Any]:
    return {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scores": {
            "logical": scene.verification.logical.score,
            "perception": scene.verification.perception.score,
            "total": scene.verification.final.total_score,
        },
        "failure_reason": scene.verification.final.failure_reason,
        "timestamps": {
            "created_at": scene.meta.created_at.isoformat(),
            "updated_at": scene.meta.updated_at.isoformat(),
        },
    }
