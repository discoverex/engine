from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from discoverex.config import PipelineConfig

FlowCommand = Literal["generate", "verify", "animate"]
SubflowHandler = Callable[..., dict[str, Any]]


def resolve_subflow(config: "PipelineConfig", command: FlowCommand) -> SubflowHandler:
    from hydra.utils import instantiate

    if config.flows is None:
        raise ValueError("flows config is required for engine entry flow")
    component = getattr(config.flows, command)
    handler = instantiate(component.as_kwargs())
    return cast(SubflowHandler, handler)
