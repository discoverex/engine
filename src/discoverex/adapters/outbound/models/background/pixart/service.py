from __future__ import annotations

from typing import Any


def predict_canvas_upscale(*, output_path: Any, source_path: Any, width: int, height: int, canvas_scale_factor: float) -> Any:
    from PIL import Image  # type: ignore

    from .base import upscale_canvas

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path).convert("RGB") as image:
        upscale_canvas(image=image, width=width, height=height, canvas_scale_factor=canvas_scale_factor).save(output_path)
    return output_path


def predict_detail_reconstruct(*, model: Any, handle: Any, params: Any) -> Any:
    from PIL import Image  # type: ignore

    params.output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(params.image_ref).convert("RGB") as image:
        refined = model._reconstruct_details(handle=handle, image=image, prompt=params.prompt, negative_prompt=params.negative_prompt, seed=params.seed, num_inference_steps=params.num_inference_steps, guidance_scale=params.guidance_scale, strength=params.strength)
        if params.enable_extension:
            refined = model._reconstruct_details(handle=handle, image=refined.resize((max(1, int(round(refined.width * params.extension_scale_factor))), max(1, int(round(refined.height * params.extension_scale_factor))))), prompt=params.prompt, negative_prompt=params.negative_prompt, seed=params.seed, num_inference_steps=params.extension_steps, guidance_scale=params.extension_guidance, strength=params.extension_strength)
        refined.save(params.output_path)
    return params.output_path


def predict_hires_fix(*, model: Any, handle: Any, params: Any) -> Any:
    canvas_path = predict_canvas_upscale(output_path=params.output_path.with_suffix(".canvas.png"), source_path=params.image_ref, width=params.width, height=params.height, canvas_scale_factor=model.canvas_scale_factor)
    return predict_detail_reconstruct(model=model, handle=handle, params=params.__class__(**{**params.__dict__, "image_ref": canvas_path}))
