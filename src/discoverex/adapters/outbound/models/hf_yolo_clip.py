from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.adapters.outbound.models.cv_color_edge import compute_visual_similarity
from discoverex.models.types import (
    ColorEdgeMetadata,
    ModelHandle,
    PhysicalMetadata,
    VisualVerification,
)

_SIMILARITY_THRESHOLD = 0.75  # 색상+형상 앙상블 유사도 기준
_DIST_THRESH = 100.0  # 유사 객체 거리 기본값 (euclidean_distance_map 없을 때)


class YoloCLIPAdapter:
    """
    Phase 4: Visual difficulty verification via YOLO + CLIP (parallel load).

    VRAM strategy: both models loaded simultaneously, combined < 4 GB.
    YOLO tracks per-object sigma_threshold (disappearance blur level).
    CLIP computes DRR slope: decay rate of similarity over log(sigma) levels.
    Reuses ColorEdgeMetadata from Phase 2 for visual similarity computation.
    """

    def __init__(
        self,
        yolo_model_id: str = "THU-MIG/yolov10-n",
        clip_model_id: str = "openai/clip-vit-base-patch32",
        sigma_levels: list[float] | None = None,
        device: str = "cuda",
        max_vram_gb: float = 4.0,
        iou_match_threshold: float = 0.3,  # frozen hyperparam — step fn, not differentiable
    ) -> None:
        self._yolo_model_id = yolo_model_id
        self._clip_model_id = clip_model_id
        self._sigma_levels = sigma_levels or [1.0, 2.0, 4.0, 8.0, 16.0]
        self._device = device
        self._max_vram_gb = max_vram_gb
        self._iou_match_threshold = iou_match_threshold
        self._yolo: Any = None
        self._clip_model: Any = None
        self._clip_processor: Any = None

    # ------------------------------------------------------------------

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        from transformers import CLIPModel, CLIPProcessor
        from ultralytics import YOLO

        self._yolo = YOLO(self._yolo_model_id)
        self._yolo.to(self._device)

        self._clip_model = CLIPModel.from_pretrained(self._clip_model_id).to(
            self._device
        )
        self._clip_processor = CLIPProcessor.from_pretrained(self._clip_model_id)
        self._clip_model.eval()

    def verify(
        self,
        composite_image: Path,
        sigma_levels: list[float],
        color_edge: ColorEdgeMetadata | None = None,
        physical: PhysicalMetadata | None = None,
    ) -> VisualVerification:
        import numpy as np
        import torch
        from PIL import Image, ImageFilter

        original = Image.open(composite_image).convert("RGB")
        orig_array = np.array(original)
        W, H = original.size

        # Detect objects in original to establish baseline bounding boxes
        baseline_results = self._yolo(orig_array, verbose=False)
        baseline_boxes = baseline_results[0].boxes
        if baseline_boxes is None or len(baseline_boxes) == 0:
            return VisualVerification(
                sigma_threshold_map={},
                drr_slope_map={},
                similar_count_map={},
                similar_distance_map={},
                object_count_map={},
            )

        baseline_xyxy = baseline_boxes.xyxy.cpu().numpy()  # (n, 4) in pixel coords
        n_objects = len(baseline_xyxy)
        obj_ids = [f"obj_{i}" for i in range(n_objects)]

        # Per-object sigma_threshold: lowest σ at which IoU match drops below 0.3
        max_sigma = max(sigma_levels)
        sigma_threshold_map: dict[str, float] = {oid: max_sigma for oid in obj_ids}

        for sigma in sorted(sigma_levels):
            blurred = original.filter(ImageFilter.GaussianBlur(radius=sigma))
            results = self._yolo(np.array(blurred), verbose=False)
            detected = results[0].boxes
            detected_xyxy = (
                detected.xyxy.cpu().numpy()
                if detected is not None and len(detected) > 0
                else np.empty((0, 4))
            )

            for i, oid in enumerate(obj_ids):
                if sigma_threshold_map[oid] != max_sigma:
                    continue  # Already marked as disappeared
                base_box = baseline_xyxy[i]
                matched = any(
                    _iou(base_box, det_box) >= self._iou_match_threshold
                    for det_box in detected_xyxy
                )
                if not matched:
                    sigma_threshold_map[oid] = sigma

        # Per-object DRR slope: decay rate of CLIP similarity over log(sigma)
        # drr_slope = -slope(log(sigma), similarity) — larger = faster decay = harder
        import numpy as np

        sorted_sigmas = sorted(sigma_levels)
        log_sigmas = np.log(np.array(sorted_sigmas, dtype=float))
        drr_slope_map: dict[str, float] = {}

        for i, oid in enumerate(obj_ids):
            x1, y1, x2, y2 = (int(v) for v in baseline_xyxy[i])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(W, x2), min(H, y2)
            if x2 <= x1 or y2 <= y1:
                drr_slope_map[oid] = 0.0
                continue
            crop_orig = original.crop((x1, y1, x2, y2))
            similarities = []
            for sigma in sorted_sigmas:
                blurred = original.filter(ImageFilter.GaussianBlur(radius=sigma))
                crop_blur = blurred.crop((x1, y1, x2, y2))
                feat_orig = self._clip_image_features(crop_orig)
                feat_blur = self._clip_image_features(crop_blur)
                with torch.no_grad():
                    sim = torch.nn.functional.cosine_similarity(
                        feat_orig, feat_blur, dim=-1
                    ).item()
                similarities.append(float(max(0.0, min(1.0, sim))))
            slope, _ = np.polyfit(log_sigmas, similarities, 1)
            drr_slope_map[oid] = float(max(0.0, -slope))

        # object_count_map: YOLO baseline detection count per object (= 1 each from baseline)
        object_count_map: dict[str, int] = {oid: 1 for oid in obj_ids}

        # similar_count_map / similar_distance_map: visual similarity using Phase 2 data
        similar_count_map: dict[str, int] = {}
        similar_distance_map: dict[str, float] = {}

        if color_edge is not None and color_edge.obj_color_map:
            ce_obj_ids = list(color_edge.obj_color_map.keys())
            for oid in obj_ids:
                if oid not in color_edge.obj_color_map:
                    similar_count_map[oid] = 0
                    similar_distance_map[oid] = _DIST_THRESH
                    continue
                sim_count = 0
                dist_sum = 0.0
                for other in ce_obj_ids:
                    if other == oid:
                        continue
                    if other not in color_edge.obj_color_map:
                        continue
                    sim = compute_visual_similarity(
                        color_edge.obj_color_map[oid],
                        color_edge.obj_color_map[other],
                        color_edge.hu_moments_map.get(oid, [0.0] * 7),
                        color_edge.hu_moments_map.get(other, [0.0] * 7),
                    )
                    if sim >= _SIMILARITY_THRESHOLD:
                        sim_count += 1
                        # euclidean distance from physical if available
                        if (
                            physical is not None
                            and oid in physical.euclidean_distance_map
                        ):
                            dists = physical.euclidean_distance_map[oid]
                            dist_sum += float(dists[0]) if dists else _DIST_THRESH
                        else:
                            dist_sum += _DIST_THRESH
                similar_count_map[oid] = sim_count
                similar_distance_map[oid] = (
                    dist_sum / sim_count if sim_count > 0 else _DIST_THRESH
                )
        else:
            for oid in obj_ids:
                similar_count_map[oid] = 0
                similar_distance_map[oid] = _DIST_THRESH

        return VisualVerification(
            sigma_threshold_map=sigma_threshold_map,
            drr_slope_map=drr_slope_map,
            similar_count_map=similar_count_map,
            similar_distance_map=similar_distance_map,
            object_count_map=object_count_map,
        )

    def unload(self) -> None:
        import gc

        import torch

        del self._yolo
        del self._clip_model
        del self._clip_processor
        self._yolo = None
        self._clip_model = None
        self._clip_processor = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------

    def _clip_image_features(self, image: Any) -> Any:
        import torch

        inputs = self._clip_processor(images=image, return_tensors="pt").to(
            self._device
        )
        with torch.no_grad():
            features = self._clip_model.get_image_features(**inputs)
        return features


# ------------------------------------------------------------------


def _iou(box_a: Any, box_b: Any) -> float:
    """Intersection-over-Union for two [x1, y1, x2, y2] boxes."""
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
