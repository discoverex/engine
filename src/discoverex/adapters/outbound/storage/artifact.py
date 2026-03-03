from __future__ import annotations

import json
from pathlib import Path

from discoverex.domain.scene import Scene


class LocalArtifactStoreAdapter:
    def __init__(self, artifacts_root: str = "artifacts", **_: str) -> None:
        self.root_dir = Path(artifacts_root)

    def _scene_dir(self, scene: Scene) -> Path:
        return self.root_dir / "scenes" / scene.meta.scene_id / scene.meta.version_id

    def save_scene_bundle(self, scene: Scene) -> Path:
        base = self._scene_dir(scene)
        base.mkdir(parents=True, exist_ok=True)

        (base / "scene.json").write_text(
            json.dumps(
                scene.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (base / "verification.json").write_text(
            json.dumps(
                {
                    "scene_id": scene.meta.scene_id,
                    "version_id": scene.meta.version_id,
                    "status": scene.meta.status.value,
                    "verification": scene.verification.model_dump(
                        mode="json", by_alias=True
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return base


class MinioArtifactStoreAdapter:
    def __init__(
        self,
        artifacts_root: str = "artifacts",
        artifact_bucket: str = "discoverex-artifacts",
        s3_endpoint_url: str = "http://127.0.0.1:9000",
        aws_access_key_id: str = "minioadmin",
        aws_secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        **_: str,
    ) -> None:
        try:
            import boto3  # type: ignore
            from botocore.client import BaseClient  # type: ignore
            from botocore.config import Config  # type: ignore
            from botocore.exceptions import ClientError  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "boto3/botocore dependencies are required for MinioArtifactStoreAdapter. "
                "Install with `uv sync --extra storage`."
            ) from exc

        self.local = LocalArtifactStoreAdapter(artifacts_root=artifacts_root)
        self.bucket = artifact_bucket
        self._client_error_cls = ClientError
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=s3_endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except self._client_error_cls:
            self.client.create_bucket(Bucket=self.bucket)

    def _upload_scene_dir(self, scene: Scene, base: Path) -> None:
        key_prefix = f"scenes/{scene.meta.scene_id}/{scene.meta.version_id}"
        for file_path in base.glob("*"):
            if file_path.is_file():
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=f"{key_prefix}/{file_path.name}",
                    Body=file_path.read_bytes(),
                )

    def save_scene_bundle(self, scene: Scene) -> Path:
        base = self.local.save_scene_bundle(scene)
        self._upload_scene_dir(scene, base)
        return base
