from __future__ import annotations

import json

_DEFAULT_OBJECT_GENERATION_PROMPT = "isolated hidden object"
_DEFAULT_OBJECT_PROMPT_STYLE = "neutral_backdrop"
_DEFAULT_OBJECT_NEGATIVE_PROFILE = "default"

_PROMPT_STYLE_SUFFIXES = {
    "neutral_backdrop": (
        "isolated single object, centered composition, "
        "plain neutral backdrop, no environment, no floor"
    ),
    "transparent_only": (
        "isolated single object, centered composition, "
        "transparent background, cutout asset, no environment, no floor"
    ),
    "studio_cutout": (
        "isolated single object, centered composition, "
        "studio product cutout, clean edges, no environment, no floor"
    ),
}

_NEGATIVE_PROFILE_SUFFIXES = {
    "default": "",
    "anti_white": "white object, washed out, overexposed, pale colors, colorless",
    "anti_white_glow": (
        "white object, washed out, overexposed, pale colors, colorless, "
        "glow, bloom, haze"
    ),
}


def compose_prompt(*, base_prompt: str, prompt: str) -> str:
    base_text = base_prompt.strip()
    prompt_text = prompt.strip()
    if base_text and prompt_text:
        return f"{base_text}, {prompt_text}"
    return prompt_text or base_text


def object_generation_prompt(
    object_prompt: str,
    *,
    style: str = _DEFAULT_OBJECT_PROMPT_STYLE,
) -> str:
    prompt = object_prompt.strip() or _DEFAULT_OBJECT_GENERATION_PROMPT
    suffix = _PROMPT_STYLE_SUFFIXES.get(style, _PROMPT_STYLE_SUFFIXES[_DEFAULT_OBJECT_PROMPT_STYLE])
    return f"{prompt}, {suffix}"


def resolve_object_prompt_style(style: str) -> str:
    normalized = style.strip().lower()
    return normalized if normalized in _PROMPT_STYLE_SUFFIXES else _DEFAULT_OBJECT_PROMPT_STYLE


def compose_negative_prompt(
    *,
    base_negative_prompt: str,
    negative_prompt: str,
    profile: str = _DEFAULT_OBJECT_NEGATIVE_PROFILE,
) -> str:
    resolved_profile = resolve_object_negative_profile(profile)
    parts = [
        base_negative_prompt.strip(),
        negative_prompt.strip(),
        _NEGATIVE_PROFILE_SUFFIXES[resolved_profile],
    ]
    return ", ".join(part for part in parts if part)


def resolve_object_negative_profile(profile: str) -> str:
    normalized = profile.strip().lower()
    return normalized if normalized in _NEGATIVE_PROFILE_SUFFIXES else _DEFAULT_OBJECT_NEGATIVE_PROFILE


def resolve_object_prompts(object_prompt: str, *, total_regions: int) -> list[str]:
    prompts = split_object_prompts(object_prompt)
    if total_regions <= 0:
        return []
    if not prompts:
        prompts = [_DEFAULT_OBJECT_GENERATION_PROMPT]
    if len(prompts) >= total_regions:
        return prompts[:total_regions]
    padded = list(prompts)
    padded.extend([prompts[-1]] * (total_regions - len(prompts)))
    return padded


def split_object_prompts(object_prompt: str) -> list[str]:
    prompt = object_prompt.strip()
    if not prompt:
        return []
    if prompt.startswith("["):
        try:
            parsed = json.loads(prompt)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    for separator in ("\n", "|", ";"):
        if separator in prompt:
            return [part.strip() for part in prompt.split(separator) if part.strip()]
    return [prompt]
