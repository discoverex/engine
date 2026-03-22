from __future__ import annotations

from discoverex.application.use_cases.gen_verify.object_pipeline import (
    resolve_object_prompts,
)
from discoverex.application.use_cases.gen_verify.objects.prompts import compose_prompt
from discoverex.application.use_cases.gen_verify.region_pipeline import (
    build_candidate_regions,
)


def test_build_candidate_regions_skips_nearby_boxes() -> None:
    regions = build_candidate_regions(
        [
            (10.0, 10.0, 40.0, 40.0),
            (18.0, 16.0, 40.0, 40.0),
            (140.0, 120.0, 40.0, 40.0),
        ]
    )

    assert len(regions) == 2
    assert regions[0].geometry.bbox.x == 10.0
    assert regions[1].geometry.bbox.x == 140.0


def test_resolve_object_prompts_supports_multiple_objects() -> None:
    prompts = resolve_object_prompts("banana | key | compass", total_regions=3)
    assert prompts == ["banana", "key", "compass"]


def test_resolve_object_prompts_pads_last_prompt() -> None:
    prompts = resolve_object_prompts('["banana", "key"]', total_regions=4)
    assert prompts == ["banana", "key", "key", "key"]


def test_compose_prompt_joins_base_and_specific_prompt() -> None:
    assert (
        compose_prompt(base_prompt="isolated single object", prompt="butterfly")
        == "isolated single object, butterfly"
    )
