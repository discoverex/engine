from __future__ import annotations

import cv2
import numpy as np
import safetensors.torch as sf
import torch
import torch.nn as nn
from diffusers.configuration_utils import ConfigMixin, register_to_config
from diffusers.models.modeling_utils import ModelMixin
from diffusers.models.unets.unet_2d_blocks import (
    UNetMidBlock2D,
    get_down_block,
    get_up_block,
)
from tqdm import tqdm


def zero_module(module: torch.nn.Module) -> torch.nn.Module:
    for parameter in module.parameters():
        parameter.detach().zero_()
    return module


class UNet1024(ModelMixin, ConfigMixin):
    @register_to_config
    def __init__(
        self,
        in_channels: int = 3,
        out_channels: int = 3,
        down_block_types: tuple[str, ...] = (
            "DownBlock2D",
            "DownBlock2D",
            "DownBlock2D",
            "DownBlock2D",
            "AttnDownBlock2D",
            "AttnDownBlock2D",
            "AttnDownBlock2D",
        ),
        up_block_types: tuple[str, ...] = (
            "AttnUpBlock2D",
            "AttnUpBlock2D",
            "AttnUpBlock2D",
            "UpBlock2D",
            "UpBlock2D",
            "UpBlock2D",
            "UpBlock2D",
        ),
        block_out_channels: tuple[int, ...] = (32, 32, 64, 128, 256, 512, 512),
        layers_per_block: int = 2,
        mid_block_scale_factor: float = 1.0,
        downsample_padding: int = 1,
        downsample_type: str = "conv",
        upsample_type: str = "conv",
        dropout: float = 0.0,
        act_fn: str = "silu",
        attention_head_dim: int | None = 8,
        norm_num_groups: int = 4,
        norm_eps: float = 1e-5,
    ) -> None:
        super().__init__()
        self.conv_in = nn.Conv2d(
            in_channels, block_out_channels[0], kernel_size=3, padding=(1, 1)
        )
        self.latent_conv_in = zero_module(
            nn.Conv2d(4, block_out_channels[2], kernel_size=1)
        )
        self.down_blocks = nn.ModuleList([])
        self.up_blocks = nn.ModuleList([])

        output_channel = block_out_channels[0]
        for index, down_block_type in enumerate(down_block_types):
            input_channel = output_channel
            output_channel = block_out_channels[index]
            is_final_block = index == len(block_out_channels) - 1
            down_block = get_down_block(
                down_block_type,
                num_layers=layers_per_block,
                in_channels=input_channel,
                out_channels=output_channel,
                temb_channels=None,
                add_downsample=not is_final_block,
                resnet_eps=norm_eps,
                resnet_act_fn=act_fn,
                resnet_groups=norm_num_groups,
                attention_head_dim=(
                    attention_head_dim
                    if attention_head_dim is not None
                    else output_channel
                ),
                downsample_padding=downsample_padding,
                resnet_time_scale_shift="default",
                downsample_type=downsample_type,
                dropout=dropout,
            )
            self.down_blocks.append(down_block)

        self.mid_block = UNetMidBlock2D(
            in_channels=block_out_channels[-1],
            temb_channels=None,
            dropout=dropout,
            resnet_eps=norm_eps,
            resnet_act_fn=act_fn,
            output_scale_factor=mid_block_scale_factor,
            resnet_time_scale_shift="default",
            attention_head_dim=(
                attention_head_dim
                if attention_head_dim is not None
                else block_out_channels[-1]
            ),
            resnet_groups=norm_num_groups,
            attn_groups=None,
            add_attention=True,
        )

        reversed_block_out_channels = list(reversed(block_out_channels))
        output_channel = reversed_block_out_channels[0]
        for index, up_block_type in enumerate(up_block_types):
            prev_output_channel = output_channel
            output_channel = reversed_block_out_channels[index]
            input_channel = reversed_block_out_channels[
                min(index + 1, len(block_out_channels) - 1)
            ]
            is_final_block = index == len(block_out_channels) - 1
            up_block = get_up_block(
                up_block_type,
                num_layers=layers_per_block + 1,
                in_channels=input_channel,
                out_channels=output_channel,
                prev_output_channel=prev_output_channel,
                temb_channels=None,
                add_upsample=not is_final_block,
                resnet_eps=norm_eps,
                resnet_act_fn=act_fn,
                resnet_groups=norm_num_groups,
                attention_head_dim=(
                    attention_head_dim
                    if attention_head_dim is not None
                    else output_channel
                ),
                resnet_time_scale_shift="default",
                upsample_type=upsample_type,
                dropout=dropout,
            )
            self.up_blocks.append(up_block)

        self.conv_norm_out = nn.GroupNorm(
            num_channels=block_out_channels[0],
            num_groups=norm_num_groups,
            eps=norm_eps,
        )
        self.conv_act = nn.SiLU()
        self.conv_out = nn.Conv2d(block_out_channels[0], out_channels, 3, padding=1)

    def forward(self, x: torch.Tensor, latent: torch.Tensor) -> torch.Tensor:
        sample_latent = self.latent_conv_in(latent)
        sample = self.conv_in(x)
        down_block_res_samples: tuple[torch.Tensor, ...] = (sample,)
        for index, downsample_block in enumerate(self.down_blocks):
            if index == 3:
                sample = sample + sample_latent
            sample, res_samples = downsample_block(hidden_states=sample, temb=None)
            down_block_res_samples += res_samples
        sample = self.mid_block(sample, None)
        for upsample_block in self.up_blocks:
            res_samples = down_block_res_samples[-len(upsample_block.resnets) :]
            down_block_res_samples = down_block_res_samples[
                : -len(upsample_block.resnets)
            ]
            sample = upsample_block(sample, res_samples, None)
        sample = self.conv_norm_out(sample)
        sample = self.conv_act(sample)
        return self.conv_out(sample)


def checkerboard(shape: tuple[int, int]) -> np.ndarray:
    return np.indices(shape).sum(axis=0) % 2


class TransparentVAEDecoder(torch.nn.Module):
    def __init__(self, filename: str, dtype: torch.dtype = torch.float16) -> None:
        super().__init__()
        state_dict = sf.load_file(filename)
        model = UNet1024(in_channels=3, out_channels=4)
        model.load_state_dict(state_dict, strict=True)
        model.to(dtype=dtype)
        model.eval()
        self.model = model
        self.dtype = dtype

    @torch.no_grad()
    def estimate_single_pass(
        self, pixel: torch.Tensor, latent: torch.Tensor
    ) -> torch.Tensor:
        return self.model(pixel, latent)

    @torch.no_grad()
    def estimate_augmented(
        self, pixel: torch.Tensor, latent: torch.Tensor
    ) -> torch.Tensor:
        transforms = [
            (False, 0),
            (False, 1),
            (False, 2),
            (False, 3),
            (True, 0),
            (True, 1),
            (True, 2),
            (True, 3),
        ]
        results: list[torch.Tensor] = []
        for flip, rotations in tqdm(transforms):
            feed_pixel = pixel.clone()
            feed_latent = latent.clone()
            if flip:
                feed_pixel = torch.flip(feed_pixel, dims=(3,))
                feed_latent = torch.flip(feed_latent, dims=(3,))
            feed_pixel = torch.rot90(feed_pixel, k=rotations, dims=(2, 3))
            feed_latent = torch.rot90(feed_latent, k=rotations, dims=(2, 3))
            estimate = self.estimate_single_pass(feed_pixel, feed_latent).clip(0, 1)
            estimate = torch.rot90(estimate, k=-rotations, dims=(2, 3))
            if flip:
                estimate = torch.flip(estimate, dims=(3,))
            results.append(estimate)
        return torch.median(torch.stack(results, dim=0), dim=0).values

    @torch.no_grad()
    def forward(
        self, sd_vae: torch.nn.Module, latent: torch.Tensor
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        pixel = sd_vae.decode(latent).sample
        pixel = (pixel * 0.5 + 0.5).clip(0, 1).to(self.dtype)
        latent = latent.to(self.dtype)
        result_list: list[np.ndarray] = []
        vis_list: list[np.ndarray] = []
        for index in range(int(latent.shape[0])):
            estimate = self.estimate_augmented(
                pixel[index : index + 1], latent[index : index + 1]
            )
            estimate = estimate.clip(0, 1).movedim(1, -1)
            alpha = estimate[..., :1]
            foreground = estimate[..., 1:]
            _, height, width, _ = foreground.shape
            board = checkerboard(shape=(height // 64, width // 64))
            board = cv2.resize(board, (width, height), interpolation=cv2.INTER_NEAREST)
            board = (0.5 + (board - 0.5) * 0.1)[None, ..., None]
            board_tensor = torch.from_numpy(board).to(foreground)
            vis = (foreground * alpha + board_tensor * (1 - alpha))[0]
            vis_list.append(
                (vis * 255.0)
                .detach()
                .float()
                .cpu()
                .numpy()
                .clip(0, 255)
                .astype(np.uint8)
            )
            png = torch.cat([foreground, alpha], dim=3)[0]
            result_list.append(
                (png * 255.0)
                .detach()
                .float()
                .cpu()
                .numpy()
                .clip(0, 255)
                .astype(np.uint8)
            )
        return result_list, vis_list
