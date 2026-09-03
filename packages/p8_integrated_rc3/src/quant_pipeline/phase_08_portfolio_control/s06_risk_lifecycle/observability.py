from __future__ import annotations

import logging
from collections.abc import Mapping

LOGGER = logging.getLogger("quant_pipeline.p8.s6")


def log_event(event: str, fields: Mapping[str, object]) -> None:
    LOGGER.info("%s %s", event, dict(sorted(fields.items())))
