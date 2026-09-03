"""Structured logging helpers without global mutable state."""

from __future__ import annotations

import logging
from collections.abc import Mapping


class StructuredModuleLogger:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def info(self, message: str, fields: Mapping[str, object]) -> None:
        self._logger.info(message, extra={"p8": dict(fields)})

    def warning(self, message: str, fields: Mapping[str, object]) -> None:
        self._logger.warning(message, extra={"p8": dict(fields)})

    def error(self, message: str, fields: Mapping[str, object]) -> None:
        self._logger.error(message, extra={"p8": dict(fields)})
