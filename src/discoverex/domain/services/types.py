from __future__ import annotations

from typing import TypedDict


class ObjectMetrics(TypedDict):
    obj_id: str
    visual_degree: float
    logical_degree: float
    degree_norm: float
    cluster_density: float
    z_depth_hop: float
    hop: float
    diameter: float
    sigma_threshold: float
    drr_slope: float
    similar_count: int
    similar_distance: float
    color_contrast: float
    edge_strength: float


class SceneNorms(TypedDict):
    max_inv_cc: float
    max_inv_es: float
    max_hop: float
    max_cluster: float
