"""Bundle JSON → labeled JSONL 변환기.

설계안 §4 VerificationBundle JSON 파일을 읽어
WeightFitter 입력 형식의 labeled JSONL 로 변환한다.

Usage
-----
    uv run python src/ML/bundle_to_jsonl.py \\
        --bundle-dir src/ML/data/ \\
        --out src/ML/data/train.jsonl

출력 레코드 형식 (1 hidden_object = 1 레코드):
    {
        "scene_id": str,
        "obj_id": str,
        "label": int,           # 1=pass, 0=fail (bundle 최상위 pass 기준)
        "scene_difficulty": float,
        "human_field": float,
        "ai_field": float,
        "D_obj": float,
        # difficulty_signals 9개 키 flatten
        "degree_norm": float,
        "cluster_density_norm": float,
        "hop_diameter": float,
        "drr_slope_norm": float,
        "sigma_threshold_norm": float,
        "similar_count_norm": float,
        "similar_distance_norm": float,
        "color_contrast_norm": float,
        "edge_strength_norm": float,
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SIGNAL_KEYS = [
    "degree_norm",
    "cluster_density_norm",
    "hop_diameter",
    "drr_slope_norm",
    "sigma_threshold_norm",
    "similar_count_norm",
    "similar_distance_norm",
    "color_contrast_norm",
    "edge_strength_norm",
]


def _load_bundle(path: Path) -> dict | None:
    """JSON 파일 로드. 파싱 오류 시 None 반환."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[SKIP] {path}: {exc}", file=sys.stderr)
        return None


def _bundle_to_records(bundle: dict, source_path: Path) -> list[dict]:
    """단일 bundle dict → JSONL 레코드 리스트.

    `label` 필드가 없는 bundle 은 skip.
    hidden_objects 가 없거나 비어 있으면 빈 리스트 반환.
    """
    if "label" not in bundle:
        return []

    label = int(bundle["label"])
    scene_id = bundle.get("scene_id", source_path.stem)
    scene_difficulty = float(bundle.get("scene_difficulty", 0.0))
    passed = bool(bundle.get("pass", False))

    # label 이 명시되지 않은 경우 pass 필드로 보완
    if "label" not in bundle:
        label = 1 if passed else 0

    records: list[dict] = []
    for obj in bundle.get("hidden_objects", []):
        signals = obj.get("difficulty_signals", {})
        record: dict = {
            "scene_id": scene_id,
            "obj_id": obj.get("obj_id", ""),
            "label": label,
            "scene_difficulty": scene_difficulty,
            "human_field": float(obj.get("human_field", 0.0)),
            "ai_field": float(obj.get("ai_field", 0.0)),
            "D_obj": float(obj.get("D_obj", 0.0)),
        }
        for key in _SIGNAL_KEYS:
            record[key] = float(signals.get(key, 0.0))
        records.append(record)
    return records


def convert(bundle_dir: Path, out_path: Path) -> int:
    """bundle_dir 내 모든 JSON 파일을 변환해 out_path 에 JSONL 로 저장.

    Returns
    -------
    int
        출력된 레코드 총 수.
    """
    bundle_files = sorted(bundle_dir.glob("**/*.json"))
    if not bundle_files:
        print(f"[WARN] No JSON files found in {bundle_dir}", file=sys.stderr)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    skipped = 0

    with out_path.open("w", encoding="utf-8") as fout:
        for path in bundle_files:
            bundle = _load_bundle(path)
            if bundle is None:
                skipped += 1
                continue
            records = _bundle_to_records(bundle, path)
            if not records:
                skipped += 1
                continue
            for rec in records:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1

    print(
        f"[OK] {total} records written to {out_path}  ({skipped} bundles skipped)",
        file=sys.stderr,
    )
    return total


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert VerificationBundle JSON files to labeled JSONL."
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Directory containing bundle JSON files (searched recursively).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSONL file path.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    n = convert(args.bundle_dir, args.out)
    sys.exit(0 if n > 0 else 1)
