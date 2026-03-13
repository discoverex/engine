from __future__ import annotations

from pathlib import Path

import numpy as np

from discoverex.models.types import ColorEdgeMetadata, ModelHandle


class CvColorEdgeAdapter:
    """Phase 2: Classical CV color contrast and edge strength extraction.

    CPU-only, no model required. Requires opencv-python.

    Inputs : composite_image (Path) + object_layers (list[Path], RGBA PNG)
    Outputs: ColorEdgeMetadata
        color_contrast_map  — LAB ΔE 근사 (객체 vs 인접 배경 링)
        edge_strength_map   — 경계 픽셀 Sobel magnitude 평균
        obj_color_map       — 객체 LAB 평균 [L, a, b] (Phase 4 유사도 재활용)
        hu_moments_map      — Hu Moments 7차원 (Phase 4 형상 유사도 재활용)
    """

    def __init__(self) -> None:
        self.last_result: ColorEdgeMetadata | None = None

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def extract(
        self, composite_image: Path, object_layers: list[Path]
    ) -> ColorEdgeMetadata:
        from PIL import Image

        composite_rgba = np.array(Image.open(composite_image).convert("RGBA"))
        layer_arrays = [np.array(Image.open(p).convert("RGBA")) for p in object_layers]

        color_contrast_map: dict[str, float] = {}
        edge_strength_map: dict[str, float] = {}
        obj_color_map: dict[str, list[float]] = {}
        hu_moments_map: dict[str, list[float]] = {}

        for layer, layer_path in zip(layer_arrays, object_layers, strict=False):
            obj_id = layer_path.stem
            contrast, obj_color = _compute_color_contrast(layer, composite_rgba)
            strength, hu = _compute_edge_strength(layer)

            color_contrast_map[obj_id] = contrast
            edge_strength_map[obj_id] = strength
            obj_color_map[obj_id] = obj_color
            hu_moments_map[obj_id] = hu.tolist()

        result = ColorEdgeMetadata(
            color_contrast_map=color_contrast_map,
            edge_strength_map=edge_strength_map,
            obj_color_map=obj_color_map,
            hu_moments_map=hu_moments_map,
        )
        self.last_result = result
        return result

    def unload(self) -> None:
        pass


def _compute_color_contrast(
    layer_rgba: np.ndarray, composite_rgba: np.ndarray
) -> tuple[float, list[float]]:
    """객체 마스크 내부 vs 경계 외부 N픽셀 LAB 색차 + 객체 LAB 평균값 반환."""
    import cv2

    mask = layer_rgba[:, :, 3] > 0
    if not mask.any():
        return 0.0, [0.0, 0.0, 0.0]

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    dilated = cv2.dilate(mask.astype(np.uint8), kernel)
    bg_ring = dilated.astype(bool) & (~mask)

    comp_bgr = cv2.cvtColor(composite_rgba[:, :, :3], cv2.COLOR_RGB2BGR)
    comp_lab = cv2.cvtColor(comp_bgr, cv2.COLOR_BGR2LAB).astype(float)

    obj_color = comp_lab[mask].mean(axis=0)  # [L, a, b]
    if bg_ring.any():
        bg_color = comp_lab[bg_ring].mean(axis=0)
        contrast = float(np.linalg.norm(obj_color - bg_color))
    else:
        contrast = 0.0

    return contrast, obj_color.tolist()


def _compute_edge_strength(
    layer_rgba: np.ndarray,
) -> tuple[float, np.ndarray]:
    """객체 경계 픽셀의 Sobel magnitude 평균 + Hu Moments 반환."""
    import cv2

    mask = layer_rgba[:, :, 3] > 0
    if not mask.any():
        return 0.0, np.zeros(7)

    gray = cv2.cvtColor(layer_rgba[:, :, :3], cv2.COLOR_RGB2GRAY).astype(float)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.sqrt(sobelx**2 + sobely**2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    eroded = cv2.erode(mask.astype(np.uint8), kernel)
    boundary = mask & (~eroded.astype(bool))

    strength = float(magnitude[boundary].mean()) if boundary.any() else 0.0
    hu = cv2.HuMoments(cv2.moments(boundary.astype(np.uint8))).flatten()

    return strength, hu


def compute_visual_similarity(
    obj_color_i: list[float],
    obj_color_j: list[float],
    hu_i: list[float],
    hu_j: list[float],
) -> float:
    """색상(LAB 유클리드) + 형상(Hu Moments 코사인) 앙상블 유사도.

    반환: 0.0 ~ 1.0 (높을수록 유사)
    """
    arr_i = np.array(obj_color_i)
    arr_j = np.array(obj_color_j)
    # 색상 유사도 — LAB 유클리드 거리 (정규화 상수 100)
    color_sim = 1.0 - min(float(np.linalg.norm(arr_i - arr_j)) / 100.0, 1.0)

    hu_arr_i = np.array(hu_i)
    hu_arr_j = np.array(hu_j)
    denom = float(np.linalg.norm(hu_arr_i) * np.linalg.norm(hu_arr_j))
    shape_sim = float(np.dot(hu_arr_i, hu_arr_j) / denom) if denom > 0 else 0.0

    return 0.5 * color_sim + 0.5 * shape_sim
