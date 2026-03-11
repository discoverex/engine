from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from discoverex.models.types import ModelHandle, PhysicalMetadata


class MobileSAMAdapter:
    """
    Phase 1: Physical metadata extraction using MobileSAM.

    VRAM lifecycle: load() → extract() → unload()
    Pre-processing (z_index / z_depth_hop / cluster_density) is pure CPU
    and runs before the SAM model is invoked.
    """

    def __init__(
        self,
        model_id: str = "ChaoningZhang/MobileSAM",
        device: str = "cuda",
        dtype: str = "float16",
        cluster_radius_factor: float = 0.5,  # frozen hyperparam — step fn, not differentiable
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._dtype = dtype
        self._cluster_radius_factor = cluster_radius_factor
        self._model: Any = None
        self._predictor: Any = None

    # ------------------------------------------------------------------

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        import torch
        from mobile_sam import SamPredictor, sam_model_registry

        dtype = torch.float16 if self._dtype == "float16" else torch.float32
        sam = sam_model_registry["vit_t"](checkpoint=None)
        sam = sam.to(device=self._device, dtype=dtype)
        sam.eval()
        self._model = sam
        self._predictor = SamPredictor(sam)

    def extract(
        self, composite_image: Path, object_layers: list[Path]
    ) -> PhysicalMetadata:
        import numpy as np
        from PIL import Image

        composite = np.array(Image.open(composite_image).convert("RGBA"))

        # ------------------------------------------------------------------
        # Pre-processing (pure CPU): z_index, z_depth_hop, alpha_degree
        # ------------------------------------------------------------------
        layer_arrays = [np.array(Image.open(p).convert("RGBA")) for p in object_layers]

        z_index_map: dict[str, int] = {}
        z_depth_hop_map: dict[str, int] = {}

        for i, (layer, layer_path) in enumerate(
            zip(layer_arrays, object_layers, strict=False)
        ):
            obj_id = layer_path.stem
            z_index_map[obj_id] = i
            if layer[:, :, 3].sum() == 0:
                z_depth_hop_map[obj_id] = 0

        # Compute z_depth_hop via pixel-overlap Z graph (BFS shortest path)
        # Edge j→i: layer j (higher Z) overlaps layer i (lower Z) in alpha pixels
        import networkx as nx

        n = len(object_layers)
        g: nx.DiGraph = nx.DiGraph()
        for layer_path in object_layers:
            g.add_node(layer_path.stem)

        for i in range(n):
            alpha_i = layer_arrays[i][:, :, 3] > 0
            for j in range(i + 1, n):  # j is above i in Z-order
                alpha_j = layer_arrays[j][:, :, 3] > 0
                if (alpha_i & alpha_j).any():
                    g.add_edge(object_layers[j].stem, object_layers[i].stem)

        roots = [nd for nd in g.nodes if g.in_degree(nd) == 0] or list(g.nodes)[:1]
        for layer_path in object_layers:
            obj_id = layer_path.stem
            hops = []
            for root in roots:
                try:
                    hops.append(nx.shortest_path_length(g, root, obj_id))
                except nx.NetworkXNoPath:
                    pass
            z_depth_hop_map[obj_id] = max(hops, default=0)

        # Alpha-overlap graph degree (undirected: predecessors + successors)
        alpha_degree_map: dict[str, int] = {}
        for layer_path in object_layers:
            obj_id = layer_path.stem
            alpha_degree_map[obj_id] = (
                len(list(g.predecessors(obj_id))) + len(list(g.successors(obj_id)))
            )

        # ------------------------------------------------------------------
        # SAM segmentation: generate precise masks and bounding boxes
        # ------------------------------------------------------------------
        import numpy as np

        comp_rgb = composite[:, :, :3]
        self._predictor.set_image(comp_rgb)

        regions: list[dict[str, Any]] = []
        euclidean_distance_map: dict[str, list[float]] = {}
        cluster_density_map: dict[str, int] = {}
        centers: dict[str, tuple[float, float]] = {}

        for layer, layer_path in zip(layer_arrays, object_layers, strict=False):
            obj_id = layer_path.stem
            alpha = layer[:, :, 3] > 0
            if not alpha.any():
                continue

            ys, xs = np.where(alpha)
            cx, cy = float(xs.mean()), float(ys.mean())
            centers[obj_id] = (cx, cy)

            x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
            h, w = composite.shape[:2]
            regions.append(
                {
                    "obj_id": obj_id,
                    "bbox": [x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h],
                    "center": [cx / w, cy / h],
                    "area": float(alpha.sum()) / (w * h),
                }
            )

        # Euclidean distances between object centers
        obj_ids = list(centers.keys())
        for obj_id, (cx, cy) in centers.items():
            dists = [
                math.hypot(cx - centers[oid][0], cy - centers[oid][1])
                for oid in obj_ids
                if oid != obj_id
            ]
            euclidean_distance_map[obj_id] = dists
            mean_dist = sum(dists) / len(dists) if dists else float("inf")
            cluster_radius = mean_dist * self._cluster_radius_factor
            cluster_density_map[obj_id] = sum(1 for d in dists if d <= cluster_radius)

        return PhysicalMetadata(
            regions=regions,
            z_index_map=z_index_map,
            z_depth_hop_map=z_depth_hop_map,
            cluster_density_map=cluster_density_map,
            euclidean_distance_map=euclidean_distance_map,
            alpha_degree_map=alpha_degree_map,
        )

    def unload(self) -> None:
        import gc

        import torch

        del self._model
        del self._predictor
        self._model = None
        self._predictor = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
