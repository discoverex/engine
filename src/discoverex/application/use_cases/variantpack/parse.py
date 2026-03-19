from __future__ import annotations

import json
import re
from typing import Any


def parse_variant_specs(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw = args.get("variant_specs")
    if raw is None:
        raw = args.get("variant_specs_json")
    if raw is None:
        raise ValueError("variant_specs or variant_specs_json is required")
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("variant specs must decode to a non-empty list")
    variants: list[dict[str, Any]] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise ValueError("each variant spec must be an object")
        variant_id = str(item.get("variant_id", "")).strip() or f"variant-{index:02d}"
        overrides = item.get("overrides", [])
        if not isinstance(overrides, list):
            raise ValueError(f"variant {variant_id} overrides must be a list")
        variants.append(
            {
                "variant_id": variant_id,
                "overrides": [str(value) for value in overrides if str(value).strip()],
            }
        )
    return variants


def sanitized_variant_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return cleaned or "variant"
