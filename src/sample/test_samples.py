#!/usr/bin/env python3
"""test_samples.py — PNG 샘플 이미지로 Validator 파이프라인 테스트

알파채널 생성 방식
------------------
1. PIL quantize(색상 군집화)로 이미지를 N개 색 영역으로 분할
2. 각 영역 마스크를 MaxFilter로 팽창 → 인접 레이어 간 overlap 생성
3. 레이어 순서(Z-index)가 낮은 레이어를 높은 레이어가 가리는 구조

실행:
    cd engine
    python src/sample/test_samples.py
    python src/sample/test_samples.py --n-clusters 8 --dilation 15
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx
import numpy as np
from PIL import Image, ImageFilter

from discoverex.adapters.outbound.models.cv_color_edge import (
    CvColorEdgeAdapter,
    compute_visual_similarity,
)
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.services.verification import ScoringWeights
from discoverex.models.types import (
    ColorEdgeMetadata,
    LogicalStructure,
    ModelHandle,
    PhysicalMetadata,
    VisualVerification,
)

# ---------------------------------------------------------------------------
# 알파채널(레이어) 생성
# ---------------------------------------------------------------------------


def make_alpha_layers(
    composite_path: Path,
    n_clusters: int = 6,
    dilation_px: int = 10,
    min_area_ratio: float = 0.01,
) -> tuple[list[Path], list[np.ndarray]]:
    """색상 군집화 + 마스크 팽창으로 RGBA 레이어 PNG 생성.

    Returns:
        layer_paths : 저장된 PNG 파일 경로 목록 (Z-index 오름차순)
        layer_arrays: 각 레이어의 numpy RGBA 배열 목록
    """
    out_dir = composite_path.parent / "layers" / composite_path.stem
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    img = Image.open(composite_path).convert("RGB")
    arr = np.array(img)
    h, w = arr.shape[:2]

    # 색상 군집화 (PIL median-cut)
    quantized = img.quantize(colors=n_clusters, method=Image.Quantize.MEDIANCUT)
    indices = np.array(quantized)  # shape (H, W)

    layer_paths: list[Path] = []
    layer_arrays: list[np.ndarray] = []
    kernel_size = dilation_px * 2 + 1  # MaxFilter는 홀수 크기

    for cluster_id in sorted(np.unique(indices)):
        raw_mask = indices == cluster_id
        if raw_mask.sum() < h * w * min_area_ratio:
            continue  # 너무 작은 영역 스킵

        # 마스크 팽창 → 인접 레이어와 overlap 생성
        mask_img = Image.fromarray((raw_mask * 255).astype(np.uint8))
        dilated_img = mask_img.filter(ImageFilter.MaxFilter(size=kernel_size))
        dilated = np.array(dilated_img) > 128

        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[:, :, :3] = arr
        rgba[:, :, 3] = (dilated * 255).astype(np.uint8)

        idx = len(layer_paths)
        out_path = out_dir / f"obj_{idx:02d}.png"
        Image.fromarray(rgba, mode="RGBA").save(out_path)

        orig_px = int(raw_mask.sum())
        dil_px = int(dilated.sum())
        print(f"    obj_{idx:02d}.png  원본={orig_px:,}px → 팽창={dil_px:,}px")

        layer_paths.append(out_path)
        layer_arrays.append(rgba)

    return layer_paths, layer_arrays


# ---------------------------------------------------------------------------
# PHASE 1 — CPU-only 어댑터 (MobileSAM 없이)
# ---------------------------------------------------------------------------


class CpuPhysicalAdapter:
    """alpha overlap 기반 물리 메타데이터 실계산.

    z_depth_hop: Z-graph BFS (overlap 있으면 edge 생성)
    cluster_density: center 간 거리 + cluster_radius_factor 적용
    alpha_degree: alpha-overlap 그래프의 undirected node degree
    """

    def __init__(
        self,
        layer_arrays: list[np.ndarray],
        cluster_radius_factor: float = 0.5,
    ) -> None:
        self._pre_arrays = layer_arrays
        self._factor = cluster_radius_factor
        self.last_result: PhysicalMetadata | None = None
        self.last_alpha_degree_map: dict[str, int] = {}
        self.last_diameter: float = 2.0

    def load(self, handle: ModelHandle) -> None:
        print("  [PHASE 1] CPU-only — z_hop/density/degree 실계산")

    def extract(
        self, composite_image: Path, object_layers: list[Path]
    ) -> PhysicalMetadata:
        layer_arrays = self._pre_arrays
        n = len(layer_arrays)
        composite = np.array(Image.open(composite_image).convert("RGBA"))
        h, w = composite.shape[:2]

        alphas = [la[:, :, 3] > 0 for la in layer_arrays]

        z_index_map: dict[str, int] = {}
        z_depth_hop_map: dict[str, int] = {}
        centers: dict[str, tuple[float, float]] = {}
        cluster_density_map: dict[str, int] = {}
        euclidean_distance_map: dict[str, list[float]] = {}
        regions: list[dict] = []

        for i, path in enumerate(object_layers):
            obj_id = path.stem
            alpha_i = alphas[i]
            total_px = int(alpha_i.sum())
            z_index_map[obj_id] = i

            if total_px == 0:
                z_depth_hop_map[obj_id] = 0
                continue

            ys, xs = np.where(alpha_i)
            cx, cy = float(xs.mean()), float(ys.mean())
            centers[obj_id] = (cx, cy)

            x1, y1 = int(xs.min()), int(ys.min())
            x2, y2 = int(xs.max()), int(ys.max())
            regions.append(
                {
                    "obj_id": obj_id,
                    "bbox": [x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h],
                    "center": [cx / w, cy / h],
                    "area": float(alpha_i.sum()) / (w * h),
                }
            )

        # Z-depth hop: overlap → directed edge (j is above i → j→i)
        g: nx.DiGraph = nx.DiGraph()
        for path in object_layers:
            g.add_node(path.stem)
        for i in range(n):
            for j in range(i + 1, n):
                if (alphas[i] & alphas[j]).any():
                    g.add_edge(object_layers[j].stem, object_layers[i].stem)

        roots = [nd for nd in g.nodes if g.in_degree(nd) == 0] or list(g.nodes)[:1]
        for path in object_layers:
            obj_id = path.stem
            hops = []
            for root in roots:
                try:
                    hops.append(nx.shortest_path_length(g, root, obj_id))
                except nx.NetworkXNoPath:
                    pass
            z_depth_hop_map[obj_id] = max(hops, default=0)

        # Alpha-overlap graph degree (undirected: count of overlapping neighbors)
        alpha_degree_map: dict[str, int] = {}
        for path in object_layers:
            obj_id = path.stem
            alpha_degree_map[obj_id] = len(list(g.predecessors(obj_id))) + len(
                list(g.successors(obj_id))
            )

        # Graph diameter (longest shortest path among reachable node pairs)
        try:
            ug = g.to_undirected()
            if nx.is_connected(ug):
                graph_diameter = float(nx.diameter(ug))
            else:
                largest_cc = max(nx.connected_components(ug), key=len)
                graph_diameter = float(nx.diameter(ug.subgraph(largest_cc)))
        except Exception:
            graph_diameter = float(max(z_depth_hop_map.values(), default=1))

        self.last_alpha_degree_map = alpha_degree_map
        self.last_diameter = max(graph_diameter, 2.0)

        # Cluster density
        obj_ids = list(centers.keys())
        for obj_id, (cx, cy) in centers.items():
            dists = [
                math.hypot(cx - centers[oid][0], cy - centers[oid][1])
                for oid in obj_ids
                if oid != obj_id
            ]
            euclidean_distance_map[obj_id] = dists
            mean_dist = sum(dists) / len(dists) if dists else float("inf")
            radius = mean_dist * self._factor
            cluster_density_map[obj_id] = sum(1 for d in dists if d <= radius)

        result = PhysicalMetadata(
            regions=regions,
            z_index_map=z_index_map,
            z_depth_hop_map=z_depth_hop_map,
            cluster_density_map=cluster_density_map,
            euclidean_distance_map=euclidean_distance_map,
            alpha_degree_map=alpha_degree_map,
        )
        self.last_result = result
        return result

    def unload(self) -> None:
        print("  [PHASE 1] 완료")


# ---------------------------------------------------------------------------
# PHASE 3 — 스마트 더미 (논리)
# ---------------------------------------------------------------------------


class SmartLogicalAdapter:
    """Phase 1 실계산 데이터를 재활용하는 논리 추출 어댑터.

    hop_map   : CpuPhysicalAdapter의 BFS z_depth_hop_map 재활용 (실계산)
    degree_map: alpha-overlap 그래프의 node degree 재활용 (실계산)
    diameter  : alpha-overlap 그래프의 직경 재활용 (실계산)
    (Moondream2 의미론적 관계 추출은 생략 — GPU 필요)
    """

    def __init__(self, physical_adapter: CpuPhysicalAdapter) -> None:
        self._physical = physical_adapter

    def load(self, handle: ModelHandle) -> None:
        print("  [PHASE 3] SmartLogical — Moondream2 생략, Phase 1 BFS/degree 재활용")

    def extract(
        self, composite_image: Path, physical: PhysicalMetadata
    ) -> LogicalStructure:
        obj_ids = sorted(physical.alpha_degree_map.keys())
        hop_map = {oid: physical.z_depth_hop_map.get(oid, 0) for oid in obj_ids}
        degree_map = {oid: physical.alpha_degree_map.get(oid, 0) for oid in obj_ids}
        diameter = self._physical.last_diameter
        return LogicalStructure(
            relations=[],
            degree_map=degree_map,
            hop_map=hop_map,
            diameter=diameter,
        )

    def unload(self) -> None:
        print("  [PHASE 3] 완료")


# ---------------------------------------------------------------------------
# PHASE 4 — 스마트 더미 (시각)
# ---------------------------------------------------------------------------


class SmartVisualAdapter:
    """physical 결과의 obj_id 목록을 참조해 시각 지표 생성."""

    def __init__(self, physical_adapter: CpuPhysicalAdapter) -> None:
        self._physical = physical_adapter

    def load(self, handle: ModelHandle) -> None:
        print("  [PHASE 4] SmartDummy — YOLO+CLIP 생략 (sigma=8.0, drr_slope=0.15)")

    def verify(
        self,
        composite_image: Path,
        sigma_levels: list[float],
        color_edge: ColorEdgeMetadata | None = None,
        physical: PhysicalMetadata | None = None,
    ) -> VisualVerification:
        src = physical or self._physical.last_result
        obj_ids = list(src.alpha_degree_map.keys()) if src else ["obj_00"]

        similar_count_map: dict[str, int] = {oid: 0 for oid in obj_ids}
        similar_distance_map: dict[str, float] = {oid: 100.0 for oid in obj_ids}

        # color_edge 결과가 있으면 LAB+Hu 앙상블로 유사 객체 실계산 (CPU)
        if color_edge is not None:
            sim_threshold = 0.6  # 유사도 기준
            for oid in obj_ids:
                color_i = color_edge.obj_color_map.get(oid, [0.0, 0.0, 0.0])
                hu_i = color_edge.hu_moments_map.get(oid, [0.0] * 7)
                distances: list[float] = []
                for other in obj_ids:
                    if other == oid:
                        continue
                    color_j = color_edge.obj_color_map.get(other, [0.0, 0.0, 0.0])
                    hu_j = color_edge.hu_moments_map.get(other, [0.0] * 7)
                    sim = compute_visual_similarity(color_i, color_j, hu_i, hu_j)
                    if sim >= sim_threshold:
                        distances.append(1.0 - sim)  # 유사도 → 거리
                similar_count_map[oid] = len(distances)
                similar_distance_map[oid] = (
                    float(sum(distances) / len(distances)) * 100.0
                    if distances else 100.0
                )

        return VisualVerification(
            sigma_threshold_map={oid: 8.0 for oid in obj_ids},
            drr_slope_map={oid: 0.15 for oid in obj_ids},
            similar_count_map=similar_count_map,
            similar_distance_map=similar_distance_map,
            object_count_map={oid: 1 for oid in obj_ids},
        )

    def unload(self) -> None:
        print("  [PHASE 4] 완료")


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------


def _bar(c: str = "-", n: int = 64) -> str:
    return c * n


def _print_phase1(result: PhysicalMetadata) -> None:
    print(_bar())
    print("PHASE 1 실계산값")
    print(_bar())
    print(
        f"  {'obj_id':<12} {'z_depth_hop':>12} {'cluster_density':>16} {'alpha_deg':>10}"
    )
    print("  " + _bar("-", 55))
    for oid in sorted(result.alpha_degree_map):
        print(
            f"  {oid:<12}"
            f" {result.z_depth_hop_map.get(oid, 0):>12}"
            f" {result.cluster_density_map.get(oid, 0):>16}"
            f" {result.alpha_degree_map.get(oid, 0):>10}"
        )


def _print_bundle(bundle: object) -> None:
    if not hasattr(bundle, "logical") or not hasattr(bundle, "perception"):
        raise TypeError("bundle must expose logical/perception/final attributes")
    sigs = bundle.logical.signals
    psigs = bundle.perception.signals
    print(_bar("="))
    print(f"  pass             : {bundle.final.pass_}")
    print(f"  total_score      : {bundle.final.total_score:.4f}  (기준 0.23)")
    print(f"  perception score : {bundle.perception.score:.4f}")
    print(f"  logical score    : {bundle.logical.score:.4f}")
    print(_bar())
    print(f"  answer_obj_count : {sigs['answer_obj_count']}  (숨어있다고 판단된 객체)")
    print(f"  scene_difficulty : {sigs['scene_difficulty']:.4f}")
    print(f"  alpha_degree_map : {sigs['alpha_degree_map']}")
    print(f"  hop_map          : {sigs['hop_map']}")
    print(f"  sigma_map        : {psigs.get('sigma_threshold_map', {})}")
    print(f"  drr_map          : {psigs.get('drr_slope_map', {})}")
    print(f"  similar_count    : {psigs.get('similar_count_map', {})}")
    print(f"  similar_dist     : {psigs.get('similar_distance_map', {})}")


# ---------------------------------------------------------------------------
# 이미지 1개 처리
# ---------------------------------------------------------------------------


def process_image(
    composite_path: Path,
    n_clusters: int,
    dilation_px: int,
) -> None:
    print()
    print(_bar("="))
    print(f"  이미지: {composite_path.name}")
    print(_bar("="))

    print(f"\n  [레이어 생성]  n_clusters={n_clusters}, dilation={dilation_px}px")
    layer_paths, layer_arrays = make_alpha_layers(
        composite_path, n_clusters=n_clusters, dilation_px=dilation_px
    )
    print(f"  총 {len(layer_paths)}개 레이어 → {layer_paths[0].parent}")

    handle = ModelHandle(name="cpu_test", version="v0", runtime="cpu")
    physical_adapter = CpuPhysicalAdapter(layer_arrays)
    visual_adapter = SmartVisualAdapter(physical_adapter)

    orch = ValidatorOrchestrator(
        physical_port=physical_adapter,
        color_edge_port=CvColorEdgeAdapter(),
        logical_port=SmartLogicalAdapter(physical_adapter),
        visual_port=visual_adapter,
        physical_handle=handle,
        color_edge_handle=handle,
        logical_handle=handle,
        visual_handle=handle,
        pass_threshold=0.23,
        scoring_weights=ScoringWeights(),
    )

    print()
    bundle = orch.run(composite_image=composite_path, object_layers=layer_paths)

    print()
    _print_phase1(physical_adapter.last_result)  # type: ignore[arg-type]
    print()
    _print_bundle(bundle)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="PNG 샘플 이미지 Validator 테스트")
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=6,
        help="색상 군집 수 = 생성할 레이어 수 (기본 6)",
    )
    parser.add_argument(
        "--dilation",
        type=int,
        default=10,
        help="마스크 팽창 픽셀 수 (기본 10, 클수록 overlap↑)",
    )
    args = parser.parse_args()

    sample_dir = Path(__file__).parent
    images = sorted(sample_dir.glob("sample_*.png"))

    if not images:
        print(f"[ERROR] PNG 파일 없음: {sample_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"샘플 이미지 {len(images)}개 발견")
    for img_path in images:
        process_image(img_path, n_clusters=args.n_clusters, dilation_px=args.dilation)

    print()
    print(_bar("="))
    print("완료")
    print(_bar("="))


if __name__ == "__main__":
    main()
