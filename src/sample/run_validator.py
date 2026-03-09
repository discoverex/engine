#!/usr/bin/env python3
"""run_validator.py — 실제 이미지로 Validator 파이프라인 실행

사용법
------
    cd engine
    python src/sample/run_validator.py

구조
----
    src/sample/합본.png          → composite_image
    src/sample/layer/배경.png    → 자동 제외 (hidden object 아님)
    src/sample/layer/*.png       → object_layers (알파채널 기반 실계산)

Phase 구성
----------
    Phase 1 (물리) : CpuPhysicalAdapter — RGBA alpha overlap 기반 실계산
    Phase 2 (논리) : SmartLogicalAdapter — 레이어 수 기반 SmartDummy
    Phase 3 (시각) : SmartVisualAdapter — sigma=8.0 / drr_slope=0.15 고정
    Phase 4 (판정) : 실계산 (integrate_verification_v2)

옵션
----
    --include-bg   : 배경.png 도 object_layer 에 포함
    --layer-order  : 레이어 Z-index 순서 지정 (파일명, 공백 구분)
                     예: --layer-order 쥐구멍.png MARS.png 고양이1.png
    --threshold    : pass 기준 점수 (기본 0.23)
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.services.verification import ScoringWeights
from discoverex.models.types import ModelHandle
from sample.test_samples import CpuPhysicalAdapter, SmartLogicalAdapter, SmartVisualAdapter

# ---------------------------------------------------------------------------
# 출력 유틸
# ---------------------------------------------------------------------------

BAR_WIDE = "=" * 64
BAR_THIN = "-" * 64


def _section(title: str) -> None:
    print(f"\n{BAR_WIDE}")
    print(f"  {title}")
    print(BAR_WIDE)


def _print_phase1(physical_result, layer_files: list[Path]) -> None:
    _section("PHASE 1 — 물리 메타데이터 (실계산)")
    header = f"  {'파일명':<20} {'occlusion':>10} {'z_depth_hop':>12} {'neighbors':>10}"
    print(header)
    print("  " + BAR_THIN)
    for path in layer_files:
        oid = path.stem
        occ = physical_result.occlusion_map.get(oid, 0.0)
        hop = physical_result.z_depth_hop_map.get(oid, 0)
        nbr = physical_result.cluster_density_map.get(oid, 0)
        print(f"  {path.name:<20} {occ:>10.3f} {hop:>12} {nbr:>10}")


def _print_result(bundle, layer_files: list[Path]) -> None:
    sigs  = bundle.logical.signals
    psigs = bundle.perception.signals

    _section("PHASE 4 — 최종 결과")
    verdict = "✅ PASS" if bundle.final.pass_ else "❌ FAIL"
    print(f"  {verdict}")
    print(f"  total_score      : {bundle.final.total_score:.4f}")
    print(f"  perception score : {bundle.perception.score:.4f}  (sigma + drr_slope)")
    print(f"  logical score    : {bundle.logical.score:.4f}  (hop + degree)")
    if bundle.final.failure_reason:
        print(f"  failure_reason   : {bundle.final.failure_reason}")

    print()
    print(f"  answer_obj_count : {sigs['answer_obj_count']}  (숨어있다고 판단된 오브젝트)")
    print(f"  scene_difficulty : {sigs['scene_difficulty']:.4f}")
    print(f"  diameter         : {sigs.get('diameter', '-')}")

    print()
    print("  per-object 상세:")
    header2 = f"  {'파일명':<20} {'hop':>5} {'degree':>7} {'sigma':>7} {'drr_slope':>10}"
    print(header2)
    print("  " + BAR_THIN)
    sigma_map  = psigs.get("sigma_threshold_map", {})
    drr_map    = psigs.get("drr_slope_map", {})
    hop_map    = sigs.get("hop_map", {})
    degree_map = sigs.get("degree_map", {})
    for path in layer_files:
        oid = path.stem
        print(
            f"  {path.name:<20}"
            f" {hop_map.get(oid, 0):>5}"
            f" {degree_map.get(oid, 0):>7}"
            f" {sigma_map.get(oid, '-'):>7}"
            f" {drr_map.get(oid, '-'):>10}"
        )


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="실제 이미지로 Validator 파이프라인 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--include-bg",
        action="store_true",
        help="배경.png 도 object_layer 에 포함 (기본: 제외)",
    )
    parser.add_argument(
        "--layer-order",
        nargs="+",
        metavar="FILENAME",
        help="레이어 Z-index 순서 지정. 앞=아래(피가림), 뒤=위(가림). "
             "예: --layer-order 쥐구멍.png MARS.png 고양이1.png",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.23,
        help="pass 기준 점수 (기본 0.23)",
    )
    args = parser.parse_args()

    sample_dir = Path(__file__).resolve().parent
    composite  = sample_dir / "합본.png"
    layer_dir  = sample_dir / "layer"

    if not composite.exists():
        print(f"[ERROR] 합본.png 없음: {composite}", file=sys.stderr)
        sys.exit(1)
    if not layer_dir.is_dir():
        print(f"[ERROR] layer/ 디렉터리 없음: {layer_dir}", file=sys.stderr)
        sys.exit(1)

    # 레이어 파일 목록 결정
    if args.layer_order:
        layer_files = []
        for name in args.layer_order:
            p = layer_dir / name
            if not p.exists():
                print(f"[ERROR] 레이어 파일 없음: {p}", file=sys.stderr)
                sys.exit(1)
            layer_files.append(p)
    else:
        layer_files = sorted(
            p for p in layer_dir.glob("*.png")
            if args.include_bg or p.name != "배경.png"
        )

    if not layer_files:
        print("[ERROR] object_layer 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 파일 정보 출력
    _section("입력 파일")
    print(f"  composite : {composite.name}  {Image.open(composite).size}")
    print(f"  layers    : {len(layer_files)}개")
    for i, p in enumerate(layer_files):
        im = Image.open(p)
        print(f"    [{i}] {p.name}  {im.size}  mode={im.mode}")

    # RGBA 배열 로드
    layer_arrays = [np.array(Image.open(p).convert("RGBA")) for p in layer_files]

    # 어댑터 구성
    handle = ModelHandle(name="cpu", version="v0", runtime="cpu")
    phys   = CpuPhysicalAdapter(layer_arrays)
    logic  = SmartLogicalAdapter(phys)   # Phase 1 BFS/degree 실계산값 재활용
    vis    = SmartVisualAdapter(phys)

    orch = ValidatorOrchestrator(
        physical_port=phys,
        logical_port=logic,
        visual_port=vis,
        physical_handle=handle,
        logical_handle=handle,
        visual_handle=handle,
        pass_threshold=args.threshold,
        scoring_weights=ScoringWeights(),
    )

    print()
    print(f"  pass_threshold : {args.threshold}")
    print(f"  실계산 항목    : occlusion / z_depth_hop / cluster_density / degree(alpha) / diameter")
    print(f"  더미 항목      : sigma_threshold(8.0) / drr_slope(0.15)  ← GPU/CLIP 필요")

    # 실행
    _section("파이프라인 실행")
    bundle = orch.run(composite_image=composite, object_layers=layer_files)

    # 결과 출력
    _print_phase1(phys.last_result, layer_files)
    _print_result(bundle, layer_files)

    print()
    print(BAR_WIDE)
    print("완료")
    print(BAR_WIDE)


if __name__ == "__main__":
    main()
