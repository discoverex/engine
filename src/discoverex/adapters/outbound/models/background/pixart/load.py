from __future__ import annotations

from typing import Any

from ...pipeline_memory import configure_diffusers_pipeline


def ensure_t5_tokenizer() -> None:
    try:
        from transformers import T5Tokenizer  # type: ignore

        T5Tokenizer.from_pretrained("t5-3b", legacy=False)  # type: ignore[no-untyped-call]
    except Exception:
        try:
            import importlib
            import subprocess
            import sys

            import transformers.models.t5.tokenization_t5 as tokenization_t5

            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "sentencepiece==0.1.99", "transformers==4.57.6"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            importlib.reload(tokenization_t5).T5Tokenizer.from_pretrained("t5-3b", legacy=False)  # type: ignore[no-untyped-call]
        except Exception:
            return


def load_base_pipe(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import (  # type: ignore
        DPMSolverMultistepScheduler,
        PixArtSigmaPipeline,
    )

    ensure_t5_tokenizer()
    pipe = PixArtSigmaPipeline.from_pretrained(model.model_id, revision=model.revision, torch_dtype=torch.float32 if "32" in handle.dtype else torch.float16)  # type: ignore[no-untyped-call]
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++", solver_order=2)  # type: ignore[no-untyped-call]
    return configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode=model.offload_mode,
        enable_attention_slicing=model.enable_attention_slicing,
        enable_vae_slicing=model.enable_vae_slicing,
        enable_vae_tiling=model.enable_vae_tiling,
        enable_xformers_memory_efficient_attention=model.enable_xformers_memory_efficient_attention,
        enable_fp8_layerwise_casting=model.enable_fp8_layerwise_casting,
        enable_channels_last=model.enable_channels_last,
    )


def load_detail_pipe(*, model: Any, handle: Any) -> Any:
    import torch  # type: ignore
    from diffusers import (  # type: ignore
        AutoPipelineForImage2Image,
        DPMSolverMultistepScheduler,
    )

    pipe = AutoPipelineForImage2Image.from_pretrained(model.detail_model_id, dtype=torch.float32 if "32" in handle.dtype else torch.float16)  # type: ignore[no-untyped-call]
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, algorithm_type="dpmsolver++", solver_order=2)  # type: ignore[no-untyped-call]
    return configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode=model.offload_mode,
        enable_attention_slicing=model.enable_attention_slicing,
        enable_vae_slicing=model.enable_vae_slicing,
        enable_vae_tiling=model.enable_vae_tiling,
        enable_xformers_memory_efficient_attention=model.enable_xformers_memory_efficient_attention,
        enable_fp8_layerwise_casting=model.enable_fp8_layerwise_casting,
        enable_channels_last=model.enable_channels_last,
    )
