"""가중치 학습 스크립트.

사용법
------
    python engine/src/ML/fit_weights.py \\
        --labeled-jsonl  data/labeled.jsonl \\
        --weights-out    engine/src/ML/weights.json \\
        [--weights-in    engine/src/ML/weights.json]   # 이전 학습값에서 이어 학습
        [--pass-threshold 0.35]
        [--margin        0.05]

레이블 데이터 형식 (JSONL, 한 줄 = 한 오브젝트):
    {"metrics": {"sigma_threshold": 2.0, "detail_retention_rate": 0.3,
                 "hop": 2, "diameter": 4.0, "degree_norm": 0.7}, "label": true}
    {"metrics": {"sigma_threshold": 8.0, "detail_retention_rate": 0.9,
                 "hop": 0, "diameter": 4.0, "degree_norm": 0.1}, "label": false}

출력
----
    weights.json  — 학습된 ScoringWeights (engine/conf/validator.yaml 의
                    weights_path 에 지정하면 추론 시 자동 로드)
    stdout        — {"weights_path": "...", "final_loss": 0.012, "n_samples": N}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# engine 패키지 경로 추가 (editable install 없이도 동작)
# 이 파일 위치: engine/src/ML/fit_weights.py
# engine/src/ 는 parent.parent
_ENGINE_SRC = Path(__file__).resolve().parent.parent
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

from discoverex.domain.services.verification import ScoringWeights  # noqa: E402
from ML.weight_fitter import WeightFitter  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ScoringWeights 학습 스크립트")
    p.add_argument("--labeled-jsonl", required=True, type=Path,
                   help="레이블 데이터 JSONL 파일 경로")
    p.add_argument("--weights-out", required=True, type=Path,
                   help="학습된 가중치를 저장할 JSON 경로")
    p.add_argument("--weights-in", type=Path, default=None,
                   help="초기 가중치 JSON (없으면 ScoringWeights 기본값 사용)")
    p.add_argument("--pass-threshold", type=float, default=0.35)
    p.add_argument("--margin", type=float, default=0.05,
                   help="hinge loss 마진 (기본 0.05)")
    p.add_argument("--max-iter", type=int, default=5000)
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    # 레이블 데이터 로드
    lines = args.labeled_jsonl.read_text(encoding="utf-8").strip().splitlines()
    labeled: list[tuple[dict, bool]] = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        labeled.append((obj["metrics"], bool(obj["label"])))

    if not labeled:
        print(json.dumps({"error": "레이블 데이터가 비어 있습니다."}), flush=True)
        sys.exit(1)

    # 초기 가중치 로드
    init_weights: ScoringWeights | None = None
    if args.weights_in is not None:
        init_weights = ScoringWeights.model_validate_json(
            args.weights_in.read_text(encoding="utf-8")
        )

    # 학습
    fitter = WeightFitter()
    optimised = fitter.fit(
        labeled=labeled,
        init_weights=init_weights,
        margin=args.margin,
        pass_threshold=args.pass_threshold,
        max_iter=args.max_iter,
    )

    # 저장
    args.weights_out.parent.mkdir(parents=True, exist_ok=True)
    args.weights_out.write_text(optimised.model_dump_json(indent=2), encoding="utf-8")

    # 결과 출력
    result = {
        "weights_path": str(args.weights_out),
        "n_samples": len(labeled),
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
