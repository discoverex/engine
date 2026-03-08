from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.models.types import InpaintRequest, ModelHandle

from .image_patch_ops import crop_bbox, load_image_rgb, sanitize_bbox
from .runtime import resolve_runtime


def generate_patch_with_diffusers(
    *,
    pipe: Any | None,
    generation_model_id: str,
    revision: str,
    handle: ModelHandle,
    request: InpaintRequest,
    patch_image: Any,
    generation_strength: float,
    generation_steps: int,
    generation_guidance_scale: float,
) -> tuple[Any, Any]:
    try:
        import torch  # type: ignore
        from diffusers import StableDiffusionImg2ImgPipeline  # type: ignore
    except Exception as exc:
        raise RuntimeError("diffusers runtime unavailable") from exc

    local_pipe = pipe
    if local_pipe is None:
        built = StableDiffusionImg2ImgPipeline.from_pretrained(
            generation_model_id,
            revision=revision,
            torch_dtype=torch.float32 if "32" in handle.dtype else torch.float16,
            safety_checker=None,
            feature_extractor=None,
            requires_safety_checker=False,
        )
        local_pipe = built.to(handle.device)

    prompt = request.generation_prompt or request.prompt or "repair hidden object area"
    result = local_pipe(
        prompt=prompt,
        image=patch_image,
        strength=float(request.generation_strength or generation_strength),
        num_inference_steps=int(request.generation_steps or generation_steps),
        guidance_scale=float(
            request.generation_guidance_scale or generation_guidance_scale
        ),
    )
    images = getattr(result, "images", None)
    if not images:
        raise RuntimeError("img2img returned no images")
    return local_pipe, images[0]


def predict_quality_score(
    *,
    classifier: Any | None,
    quality_model_id: str,
    revision: str,
    handle: ModelHandle,
    request: InpaintRequest,
) -> tuple[Any | None, float | None]:
    if not bool(handle.extra.get("runtime_available")):
        return classifier, None
    image_ref = request.image_ref
    if image_ref is None or request.bbox is None:
        return classifier, None

    image_path = Path(str(image_ref))
    if not image_path.exists():
        return classifier, None

    runtime = resolve_runtime()
    if not runtime.available or runtime.transformers is None:
        return classifier, None

    transformers = runtime.transformers
    local_classifier = classifier
    try:
        if local_classifier is None:
            device_arg = 0 if handle.device.startswith("cuda") else -1
            local_classifier = transformers.pipeline(
                "image-classification",
                model=quality_model_id,
                revision=revision,
                device=device_arg,
            )
        image = load_image_rgb(image_path)
        box = sanitize_bbox(request.bbox, image.width, image.height)
        crop = crop_bbox(image, box)
        preds = local_classifier(crop, top_k=1)
    except Exception:
        return local_classifier, None

    if not preds:
        return local_classifier, None
    score = preds[0].get("score")
    if isinstance(score, float):
        return local_classifier, max(0.0, min(1.0, score))
    return local_classifier, None
