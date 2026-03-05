"""LocalJsonBundleStore — VerificationBundle MVP 데이터 수집 어댑터.

MVP 운영 중 생성된 모든 VerificationBundle 을 JSON 파일로 저장한다.
label 필드는 null 로 초기화되며, 나중에 사용자 피드백(true/false)으로 채워
WeightFitter 학습 데이터로 활용할 수 있다.

저장 형식
---------
{store_dir}/{YYYYMMDD_HHMMSS}_{uuid8}.json

    {
      "scene_id":        "20240305_143022_a3f8b2c1",
      "timestamp":       "2024-03-05T14:30:22.123456+00:00",
      "composite_image": "/abs/path/to/composite.png",
      "object_layers":   ["/abs/path/to/obj_0.png", ...],
      "label":           null,
      "bundle": { "perception": {...}, "logical": {...}, "final": {...} }
    }
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from discoverex.domain.verification import VerificationBundle


class LocalJsonBundleStore:
    """BundleStorePort 구현체 — 로컬 파일시스템에 JSON 으로 저장."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        bundle: VerificationBundle,
        composite_image: Path,
        object_layers: list[Path],
    ) -> None:
        ts = datetime.now(tz=timezone.utc)
        scene_id = f"{ts.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        record = {
            "scene_id": scene_id,
            "timestamp": ts.isoformat(),
            "composite_image": str(composite_image),
            "object_layers": [str(p) for p in object_layers],
            "label": None,
            "bundle": bundle.model_dump(by_alias=True),
        }
        (self._store_dir / f"{scene_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
