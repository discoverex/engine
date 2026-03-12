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
    Phase 2 (CV)   : CvColorEdgeAdapter — color_contrast / edge_strength 실계산 (CPU)
    Phase 3 (논리) : SmartLogicalAdapter — Phase 1 BFS/degree 재활용
    Phase 4 (시각) : SmartVisualAdapter — sigma=8.0 / drr_slope=0.15 고정
    Phase 5 (판정) : 실계산 (integrate_verification_v2)

옵션
----
    --include-bg   : 배경.png 도 object_layer 에 포함
    --layer-order  : 레이어 Z-index 순서 지정 (파일명, 공백 구분)
                     예: --layer-order 쥐구멍.png MARS.png 고양이1.png
    --threshold    : pass 기준 점수 (기본 0.23)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discoverex.adapters.outbound.models.cv_color_edge import CvColorEdgeAdapter
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.services.verification import ScoringWeights
from discoverex.models.types import ModelHandle
from sample.test_samples import (
    CpuPhysicalAdapter,
    SmartLogicalAdapter,
    SmartVisualAdapter,
)

# ---------------------------------------------------------------------------
# GPU 자동 감지 및 어댑터 선택
# ---------------------------------------------------------------------------


def _detect_gpu() -> bool:
    """CUDA GPU 사용 가능 여부 확인."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _build_adapters(
    layer_arrays: list,
    gpu: bool,
) -> tuple:
    """GPU 가용 여부에 따라 어댑터를 자동 선택.

    Returns:
        (phys, logic, vis, handle, runtime_label)
    """
    if gpu:
        try:
            from discoverex.adapters.outbound.models.hf_mobilesam import MobileSAMAdapter
            from discoverex.adapters.outbound.models.hf_moondream2 import Moondream2Adapter
            from discoverex.adapters.outbound.models.hf_yolo_clip import YoloCLIPAdapter
            phys   = MobileSAMAdapter(device="cuda")
            logic  = Moondream2Adapter(device="cuda")
            vis    = YoloCLIPAdapter()
            handle = ModelHandle(name="gpu", version="v0", runtime="cuda")
            return phys, logic, vis, handle, "GPU"
        except ImportError as e:
            print(f"  [경고] GPU 어댑터 import 실패 ({e}) → CPU 폴백")

    # CPU 폴백
    phys   = CpuPhysicalAdapter(layer_arrays)
    logic  = SmartLogicalAdapter(phys)
    vis    = SmartVisualAdapter(phys)
    handle = ModelHandle(name="cpu", version="v0", runtime="cpu")
    return phys, logic, vis, handle, "CPU"

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
    if physical_result is None:
        return
    _section("PHASE 1 — 물리 메타데이터 (실계산)")
    header = f"  {'파일명':<20} {'z_depth_hop':>12} {'cluster_density':>16} {'alpha_deg':>10}"
    print(header)
    print("  " + BAR_THIN)
    for path in layer_files:
        oid = path.stem
        hop = physical_result.z_depth_hop_map.get(oid, 0)
        nbr = physical_result.cluster_density_map.get(oid, 0)
        deg = physical_result.alpha_degree_map.get(oid, 0)
        print(f"  {path.name:<20} {hop:>12} {nbr:>16} {deg:>10}")


def _print_phase2(color_edge_result, layer_files: list[Path]) -> None:
    _section("PHASE 2 — CV 메타데이터 (실계산)")
    header = f"  {'파일명':<20} {'color_contrast':>15} {'edge_strength':>14}"
    print(header)
    print("  " + BAR_THIN)
    for path in layer_files:
        oid = path.stem
        cc = color_edge_result.color_contrast_map.get(oid, 0.0)
        es = color_edge_result.edge_strength_map.get(oid, 0.0)
        print(f"  {path.name:<20} {cc:>15.3f} {es:>14.3f}")


def _print_result(bundle, layer_files: list[Path]) -> None:
    sigs = bundle.logical.signals
    psigs = bundle.perception.signals

    _section("PHASE 5 — 최종 결과")
    verdict = "✅ PASS" if bundle.final.pass_ else "❌ FAIL"
    print(f"  {verdict}")
    print(f"  total_score      : {bundle.final.total_score:.4f}")
    print(f"  perception score : {bundle.perception.score:.4f}  (sigma/drr/similar/color/edge)")
    print(f"  logical score    : {bundle.logical.score:.4f}  (hop/degree/cluster)")
    if bundle.final.failure_reason:
        print(f"  failure_reason   : {bundle.final.failure_reason}")

    print()
    print(
        f"  answer_obj_count : {sigs['answer_obj_count']}  (숨어있다고 판단된 오브젝트)"
    )
    print(f"  scene_difficulty : {bundle.scene_difficulty:.4f}")
    print(f"  diameter         : {sigs.get('diameter', '-')}")

    print()
    print("  per-object 상세:")
    header2 = (
        f"  {'파일명':<20} {'z_hop':>5} {'vis_deg':>8} {'log_deg':>8} {'cluster':>8}"
        f" {'sigma':>6} {'drr':>6} {'sim_cnt':>8} {'sim_dist':>9}"
        f" {'color_c':>8} {'edge_s':>8}"
    )
    print(header2)
    print("  " + BAR_THIN)
    sigma_map = psigs.get("sigma_threshold_map", {})
    drr_map = psigs.get("drr_slope_map", {})
    sim_cnt_map = psigs.get("similar_count_map", {})
    sim_dst_map = psigs.get("similar_distance_map", {})
    cc_map = psigs.get("color_contrast_map", {})
    es_map = psigs.get("edge_strength_map", {})
    hop_map = sigs.get("hop_map", {})
    vis_deg_map = sigs.get("alpha_degree_map", {})
    log_deg_map = sigs.get("logical_degree_map", {})
    cluster_map = sigs.get("cluster_density_map", {})
    for path in layer_files:
        oid = path.stem
        sim_dist = sim_dst_map.get(oid, "-")
        sim_dist_str = f"{sim_dist:.1f}" if isinstance(sim_dist, float) else str(sim_dist)
        sigma_val = sigma_map.get(oid, "-")
        sigma_str = f"{sigma_val:.1f}" if isinstance(sigma_val, float) else str(sigma_val)
        drr_val = drr_map.get(oid, "-")
        drr_str = f"{drr_val:.2f}" if isinstance(drr_val, float) else str(drr_val)
        print(
            f"  {path.name:<20}"
            f" {hop_map.get(oid, 0):>5}"
            f" {vis_deg_map.get(oid, 0):>8}"
            f" {log_deg_map.get(oid, 0):>8}"
            f" {cluster_map.get(oid, 0):>8}"
            f" {sigma_str:>6}"
            f" {drr_str:>6}"
            f" {sim_cnt_map.get(oid, 0):>8}"
            f" {sim_dist_str:>9}"
            f" {cc_map.get(oid, 0.0):>8.1f}"
            f" {es_map.get(oid, 0.0):>8.1f}"
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
        "--difficulty-min",
        type=float,
        default=0.1,
        help="난이도 하한 (기본 0.1)",
    )
    parser.add_argument(
        "--difficulty-max",
        type=float,
        default=0.9,
        help="난이도 상한 (기본 0.9)",
    )
    parser.add_argument(
        "--hidden-obj-min",
        type=int,
        default=3,
        help="최소 숨은 객체 수 (기본 3)",
    )
    args = parser.parse_args()

    sample_dir = Path(__file__).resolve().parent
    composite = sample_dir / "합본.png"
    layer_dir = sample_dir / "layer"

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
            p
            for p in layer_dir.glob("*.png")
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

    # 어댑터 자동 선택 (GPU 감지 → 없으면 CPU 폴백)
    gpu_available = _detect_gpu()
    phys, logic, vis, handle, runtime = _build_adapters(layer_arrays, gpu=gpu_available)
    color_edge = CvColorEdgeAdapter()  # Phase 2: CPU 실계산 (GPU 무관)

    orch = ValidatorOrchestrator(
        physical_port=phys,
        color_edge_port=color_edge,
        logical_port=logic,
        visual_port=vis,
        physical_handle=handle,
        color_edge_handle=handle,
        logical_handle=handle,
        visual_handle=handle,
        difficulty_min=args.difficulty_min,
        difficulty_max=args.difficulty_max,
        hidden_obj_min=args.hidden_obj_min,
        scoring_weights=ScoringWeights(),
    )

    print()
    print(f"  런타임         : {runtime}")
    print(f"  difficulty     : [{args.difficulty_min}, {args.difficulty_max}]  hidden_min={args.hidden_obj_min}")
    if runtime == "GPU":
        print(f"  실계산 항목    : 전 항목 (MobileSAM / Moondream2 / YOLO+CLIP)")
    else:
        print(f"  실계산 항목    : z_depth_hop / cluster_density / degree(alpha) / diameter")
        print(f"                   color_contrast / edge_strength / similar_count / similar_distance (CPU)")
        print(f"  더미 항목      : sigma_threshold(8.0) / drr_slope(0.15)  ← GPU/CLIP 필요")

    # 실행
    _section("파이프라인 실행")
    bundle = orch.run(composite_image=composite, object_layers=layer_files)

    # 결과 출력 (CPU 모드에서만 Phase 1 내부값 직접 접근 가능)
    _print_phase1(phys.last_result if hasattr(phys, "last_result") else None, layer_files)
    if color_edge.last_result is not None:
        _print_phase2(color_edge.last_result, layer_files)
    _print_result(bundle, layer_files)

    print()
    print(BAR_WIDE)
    print("완료")
    print(BAR_WIDE)


if __name__ == "__main__":
    main()
