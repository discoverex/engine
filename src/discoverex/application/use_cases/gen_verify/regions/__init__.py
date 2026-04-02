from .inpaint import generate_regions, object_inpaint_vram_stage
from .selection import build_candidate_regions

__all__ = [
    "build_candidate_regions",
    "generate_regions",
    "object_inpaint_vram_stage",
]
