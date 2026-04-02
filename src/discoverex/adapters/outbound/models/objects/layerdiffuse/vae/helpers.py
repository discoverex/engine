from __future__ import annotations

# mypy: ignore-errors
import numpy as np
import torch


def zero_module(module: torch.nn.Module) -> torch.nn.Module:
    for parameter in module.parameters():
        parameter.detach().zero_()
    return module


def checkerboard(shape: tuple[int, int]) -> np.ndarray:
    return np.indices(shape).sum(axis=0) % 2
