from __future__ import annotations

# mypy: ignore-errors
import torch
import torch.nn as nn
from diffusers.configuration_utils import ConfigMixin, register_to_config
from diffusers.models.modeling_utils import ModelMixin
from diffusers.models.unets.unet_2d_blocks import (
    UNetMidBlock2D,
    get_down_block,
    get_up_block,
)

from .helpers import zero_module


class UNet1024(ModelMixin, ConfigMixin):
    @register_to_config
    def __init__(
        self,
        in_channels: int = 3,
        out_channels: int = 3,
        down_block_types: tuple[str, ...] = ("DownBlock2D", "DownBlock2D", "DownBlock2D", "DownBlock2D", "AttnDownBlock2D", "AttnDownBlock2D", "AttnDownBlock2D"),
        up_block_types: tuple[str, ...] = ("AttnUpBlock2D", "AttnUpBlock2D", "AttnUpBlock2D", "UpBlock2D", "UpBlock2D", "UpBlock2D", "UpBlock2D"),
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
        self.conv_in = nn.Conv2d(in_channels, block_out_channels[0], kernel_size=3, padding=(1, 1))
        self.latent_conv_in = zero_module(nn.Conv2d(4, block_out_channels[2], kernel_size=1))
        self.down_blocks = nn.ModuleList([])
        self.up_blocks = nn.ModuleList([])
        output_channel = block_out_channels[0]
        for index, down_block_type in enumerate(down_block_types):
            input_channel = output_channel
            output_channel = block_out_channels[index]
            self.down_blocks.append(
                get_down_block(
                    down_block_type,
                    num_layers=layers_per_block,
                    in_channels=input_channel,
                    out_channels=output_channel,
                    temb_channels=None,
                    add_downsample=index != len(block_out_channels) - 1,
                    resnet_eps=norm_eps,
                    resnet_act_fn=act_fn,
                    resnet_groups=norm_num_groups,
                    attention_head_dim=attention_head_dim if attention_head_dim is not None else output_channel,
                    downsample_padding=downsample_padding,
                    resnet_time_scale_shift="default",
                    downsample_type=downsample_type,
                    dropout=dropout,
                )
            )
        self.mid_block = UNetMidBlock2D(
            in_channels=block_out_channels[-1],
            temb_channels=None,
            dropout=dropout,
            resnet_eps=norm_eps,
            resnet_act_fn=act_fn,
            output_scale_factor=mid_block_scale_factor,
            resnet_time_scale_shift="default",
            attention_head_dim=attention_head_dim if attention_head_dim is not None else block_out_channels[-1],
            resnet_groups=norm_num_groups,
            attn_groups=None,
            add_attention=True,
        )
        reversed_block_out_channels = list(reversed(block_out_channels))
        output_channel = reversed_block_out_channels[0]
        for index, up_block_type in enumerate(up_block_types):
            prev_output_channel = output_channel
            output_channel = reversed_block_out_channels[index]
            input_channel = reversed_block_out_channels[min(index + 1, len(block_out_channels) - 1)]
            self.up_blocks.append(
                get_up_block(
                    up_block_type,
                    num_layers=layers_per_block + 1,
                    in_channels=input_channel,
                    out_channels=output_channel,
                    prev_output_channel=prev_output_channel,
                    temb_channels=None,
                    add_upsample=index != len(block_out_channels) - 1,
                    resnet_eps=norm_eps,
                    resnet_act_fn=act_fn,
                    resnet_groups=norm_num_groups,
                    attention_head_dim=attention_head_dim if attention_head_dim is not None else output_channel,
                    resnet_time_scale_shift="default",
                    upsample_type=upsample_type,
                    dropout=dropout,
                )
            )
        self.conv_norm_out = nn.GroupNorm(num_channels=block_out_channels[0], num_groups=norm_num_groups, eps=norm_eps)
        self.conv_act = nn.SiLU()
        self.conv_out = nn.Conv2d(block_out_channels[0], out_channels, 3, padding=1)

    def forward(self, x: torch.Tensor, latent: torch.Tensor) -> torch.Tensor:
        conv_in_weight = self.conv_in.weight
        latent_conv_weight = self.latent_conv_in.weight
        if x.dtype != conv_in_weight.dtype or x.device != conv_in_weight.device:
            x = x.to(device=conv_in_weight.device, dtype=conv_in_weight.dtype)
        if latent.dtype != latent_conv_weight.dtype or latent.device != latent_conv_weight.device:
            latent = latent.to(device=latent_conv_weight.device, dtype=latent_conv_weight.dtype)
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
            down_block_res_samples = down_block_res_samples[: -len(upsample_block.resnets)]
            sample = upsample_block(sample, res_samples, None)
        return self.conv_out(self.conv_act(self.conv_norm_out(sample)))
