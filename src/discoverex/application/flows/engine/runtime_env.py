from __future__ import annotations

import os

from discoverex.runtime_logging import get_logger
from discoverex.settings import AppSettings, settings_log_payload

logger = get_logger("discoverex.engine")


def log_runtime_env_diagnostics(settings: AppSettings) -> None:
    payload = settings_log_payload(settings)
    logger.info("engine effective settings: %s", payload)
