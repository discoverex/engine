from __future__ import annotations

import json

_DEFAULT_OBJECT_GENERATION_PROMPT = "isolated hidden object"


def object_generation_prompt(object_prompt: str) -> str:
    prompt = object_prompt.strip() or _DEFAULT_OBJECT_GENERATION_PROMPT
    return (
        f"{prompt}, isolated single object, centered composition, "
        "plain neutral backdrop, no environment, no floor"
    )


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
