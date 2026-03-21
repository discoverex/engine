from __future__ import annotations

from pathlib import Path

from discoverex.cache_dirs import resolve_model_cache_dir

ATTN_OFFSET_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_attn.safetensors"
)
TRANSPARENT_DECODER_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_vae_transparent_decoder.safetensors"
)


def resolve_shared_cache_dir(
    raw_path: str,
    *,
    model_cache_dir: str = "",
    hf_home: str = "",
) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    base = resolve_model_cache_dir(model_cache_dir=model_cache_dir)
    parts = [part for part in path.parts if part not in {".", ".cache"}]
    if parts:
        return base.joinpath(*parts)
    base = (
        Path(hf_home).expanduser()
        if hf_home.strip()
        else Path.home() / ".cache" / "huggingface" / "discoverex"
    )
    parts = [part for part in path.parts if part not in {".", ".cache"}]
    return base.joinpath(*parts) if parts else base


def download_weight(*, cache_dir: str, url: str, filename: str) -> Path:
    from torch.hub import download_url_to_file  # type: ignore

    target = Path(cache_dir) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    temp = target.with_suffix(target.suffix + ".tmp")
    download_url_to_file(url, str(temp))
    temp.replace(target)
    return target
