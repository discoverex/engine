from __future__ import annotations

# mypy: ignore-errors
import torch
from diffusers import AutoencoderKL
from diffusers.configuration_utils import register_to_config
from diffusers.models.autoencoders.vae import DecoderOutput

from .vae.unet import UNet1024


class TransparentVAEDecoder(AutoencoderKL):
    @register_to_config
    def __init__(
        self,
        in_channels: int = 3,
        out_channels: int = 3,
        down_block_types: tuple[str, ...] = ("DownEncoderBlock2D",),
        up_block_types: tuple[str, ...] = ("UpDecoderBlock2D",),
        block_out_channels: tuple[int, ...] = (64,),
        layers_per_block: int = 1,
        act_fn: str = "silu",
        latent_channels: int = 4,
        norm_num_groups: int = 32,
        sample_size: int = 32,
        scaling_factor: float = 0.18215,
        latents_mean: tuple[float, ...] | None = None,
        latents_std: tuple[float, ...] | None = None,
        force_upcast: bool = True,
    ) -> None:
        self.mod_number: int | None = None
        super().__init__(
            in_channels=in_channels,
            out_channels=out_channels,
            down_block_types=down_block_types,
            up_block_types=up_block_types,
            block_out_channels=block_out_channels,
            layers_per_block=layers_per_block,
            act_fn=act_fn,
            latent_channels=latent_channels,
            norm_num_groups=norm_num_groups,
            sample_size=sample_size,
            scaling_factor=scaling_factor,
            latents_mean=latents_mean,
            latents_std=latents_std,
            force_upcast=force_upcast,
        )

    def set_transparent_decoder(
        self,
        state_dict: dict[str, torch.Tensor],
        *,
        mod_number: int = 1,
    ) -> None:
        model = UNet1024(in_channels=3, out_channels=4)
        model.load_state_dict(state_dict, strict=True)
        model.to(device=self.device, dtype=self.dtype)
        model.eval()
        self.transparent_decoder = model
        self.mod_number = mod_number

    @torch.no_grad()
    def estimate_single_pass(
        self,
        pixel: torch.Tensor,
        latent: torch.Tensor,
    ) -> torch.Tensor:
        return self.transparent_decoder(pixel, latent)

    @torch.no_grad()
    def estimate_augmented(
        self,
        pixel: torch.Tensor,
        latent: torch.Tensor,
    ) -> torch.Tensor:
        results: list[torch.Tensor] = []
        for flip, rotations in (
            (False, 0),
            (False, 1),
            (False, 2),
            (False, 3),
            (True, 0),
            (True, 1),
            (True, 2),
            (True, 3),
        ):
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
    def decode_preview(
        self,
        z: torch.Tensor,
        *,
        return_dict: bool = True,
        generator: torch.Generator | None = None,
    ) -> DecoderOutput | tuple[torch.Tensor]:
        return super().decode(z, return_dict=return_dict, generator=generator)

    @torch.no_grad()
    def decode(
        self,
        z: torch.Tensor,
        return_dict: bool = True,
        generator: torch.Generator | None = None,
    ) -> DecoderOutput | tuple[torch.Tensor]:
        pixel = self.decode_preview(z, return_dict=False, generator=generator)[0]
        pixel = pixel / 2 + 0.5
        output_batches: list[torch.Tensor] = []
        for index in range(int(z.shape[0])):
            if self.mod_number is None or (
                self.mod_number != 1 and index % self.mod_number != 0
            ):
                output_batches.append(
                    torch.cat(
                        (pixel[index : index + 1], torch.ones_like(pixel[index : index + 1, :1])),
                        dim=1,
                    )
                )
                continue
            estimate = self.estimate_augmented(pixel[index : index + 1], z[index : index + 1])
            estimate = estimate.clip(0, 1).movedim(1, -1)
            alpha = estimate[..., :1]
            foreground = estimate[..., 1:]
            rgba = torch.cat([foreground, alpha], dim=3).permute(0, 3, 1, 2)
            output_batches.append(rgba)
        result_pixel = torch.cat(output_batches, dim=0)
        result_pixel = (result_pixel - 0.5) * 2
        if not return_dict:
            return (result_pixel,)
        return DecoderOutput(sample=result_pixel)
