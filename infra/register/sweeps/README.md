# Sweep Layout

`infra/register/sweeps` is organized by experiment scope.

- `background_generation/`: experiments that only tune background generation
- `object_generation/`: experiments that only tune object generation
- `patch_selection/`: experiments that only tune patch selection
- `inpaint/`: experiments that only tune inpaint
- `combined/`: experiments spanning two or more stages

Current files use:

- `object_generation/` for single-stage object generation sweeps
- `combined/` for background+object generation and patch-selection+inpaint sweeps
