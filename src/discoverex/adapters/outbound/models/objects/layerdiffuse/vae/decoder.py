from __future__ import annotations

# mypy: ignore-errors
import cv2
import numpy as np
import safetensors.torch as sf
import torch
from tqdm import tqdm

from discoverex.adapters.outbound.models.model_loading import (
    load_state_dict_materialized,
)

from .helpers import checkerboard
from .unet import UNet1024


class TransparentVAEDecoder(torch.nn.Module):
    def __init__(self, filename: str, dtype: torch.dtype = torch.float16) -> None:
        super().__init__()
        model = UNet1024(in_channels=3, out_channels=4)
        load_state_dict_materialized(model, sf.load_file(filename), strict=True)
        model.to(dtype=dtype)
        model.eval()
        self.model = model
        self.dtype = dtype

    @torch.no_grad()
    def estimate_single_pass(self, pixel: torch.Tensor, latent: torch.Tensor) -> torch.Tensor:
        return self.model(pixel, latent)

    @torch.no_grad()
    def estimate_augmented(self, pixel: torch.Tensor, latent: torch.Tensor) -> torch.Tensor:
        results: list[torch.Tensor] = []
        for flip, rotations in tqdm([(False, 0), (False, 1), (False, 2), (False, 3), (True, 0), (True, 1), (True, 2), (True, 3)]):
            feed_pixel = torch.rot90(torch.flip(pixel.clone(), dims=(3,)) if flip else pixel.clone(), k=rotations, dims=(2, 3))
            feed_latent = torch.rot90(torch.flip(latent.clone(), dims=(3,)) if flip else latent.clone(), k=rotations, dims=(2, 3))
            estimate = torch.rot90(self.estimate_single_pass(feed_pixel, feed_latent).clip(0, 1), k=-rotations, dims=(2, 3))
            results.append(torch.flip(estimate, dims=(3,)) if flip else estimate)
        return torch.median(torch.stack(results, dim=0), dim=0).values

    @torch.no_grad()
    def forward(self, sd_vae: torch.nn.Module, latent: torch.Tensor) -> tuple[list[np.ndarray], list[np.ndarray]]:
        pixel = (sd_vae.decode(latent).sample * 0.5 + 0.5).clip(0, 1).to(self.dtype)
        latent = latent.to(self.dtype)
        result_list: list[np.ndarray] = []
        vis_list: list[np.ndarray] = []
        for index in range(int(latent.shape[0])):
            estimate = self.estimate_augmented(pixel[index : index + 1], latent[index : index + 1]).clip(0, 1).movedim(1, -1)
            alpha = estimate[..., :1]
            foreground = estimate[..., 1:]
            _, height, width, _ = foreground.shape
            board = checkerboard(shape=(height // 64, width // 64))
            board = (0.5 + (cv2.resize(board, (width, height), interpolation=cv2.INTER_NEAREST) - 0.5) * 0.1)[None, ..., None]
            vis = (foreground * alpha + torch.from_numpy(board).to(foreground) * (1 - alpha))[0]
            vis_list.append((vis * 255.0).detach().float().cpu().numpy().clip(0, 255).astype(np.uint8))
            result_list.append((torch.cat([foreground, alpha], dim=3)[0] * 255.0).detach().float().cpu().numpy().clip(0, 255).astype(np.uint8))
        return result_list, vis_list
