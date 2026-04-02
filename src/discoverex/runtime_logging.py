from __future__ import annotations

import logging
import os
import sys
from time import perf_counter

_FORMAT = "[engine] %(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(*, verbose: bool = False) -> None:
    env_level = os.getenv("DISCOVEREX_LOG_LEVEL", "").strip().upper()
    level_name = env_level or ("DEBUG" if verbose else "INFO")
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT, stream=sys.stderr, force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def format_seconds(start: float) -> str:
    return f"{perf_counter() - start:.2f}s"
