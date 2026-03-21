from __future__ import annotations

import json
import shutil
from pathlib import Path

from discoverex.artifact_paths import (
    composite_output_path,
    output_manifest_path,
    scene_root,
)
from discoverex.domain.scene import Scene


class LocalArtifactStoreAdapter:
    def __init__(self, artifacts_root: str = "artifacts", **_: str) -> None:
        self.root_dir = Path(artifacts_root)

    def _scene_dir(self, scene: Scene) -> Path:
        return scene_root(self.root_dir, scene.meta.scene_id, scene.meta.version_id)

    def _metadata_dir(self, scene: Scene) -> Path:
        return self._scene_dir(scene) / "metadata"

    def save_scene_bundle(self, scene: Scene) -> Path:
        scene_dir = self._scene_dir(scene)
        base = self._metadata_dir(scene)
        outputs_dir = scene_dir / "outputs"
        base.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)

        composite_path = composite_output_path(
            self.root_dir, scene.meta.scene_id, scene.meta.version_id
        )
        source_composite = Path(scene.composite.final_image_ref)
        if source_composite.exists() and source_composite.is_file():
            if source_composite.resolve() != composite_path.resolve():
                composite_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_composite, composite_path)
            scene.composite.final_image_ref = str(composite_path)

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
        (
            output_manifest_path(
                self.root_dir, scene.meta.scene_id, scene.meta.version_id
            )
        ).write_text(
            json.dumps(
                {
                    "scene_id": scene.meta.scene_id,
                    "version_id": scene.meta.version_id,
                    "pipeline_run_id": scene.meta.pipeline_run_id,
                    "status": scene.meta.status.value,
                    "created_at": scene.meta.created_at.isoformat(),
                    "updated_at": scene.meta.updated_at.isoformat(),
                    "lottie_path": None,
                    "preview_image_path": "composite.png"
                    if scene.composite.final_image_ref
                    else None,
                    "scene_path": "../metadata/scene.json",
                    "verification_path": "../metadata/verification.json",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return scene_dir


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
        scene_dir = self.local._scene_dir(scene)
        for file_path in scene_dir.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(scene_dir)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=f"{key_prefix}/{relative.as_posix()}",
                    Body=file_path.read_bytes(),
                )

    def save_scene_bundle(self, scene: Scene) -> Path:
        base = self.local.save_scene_bundle(scene)
        self._upload_scene_dir(scene, base)
        return base
