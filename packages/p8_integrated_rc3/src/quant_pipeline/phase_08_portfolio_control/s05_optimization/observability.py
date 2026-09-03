from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("module_id", "run_id", "cycle_id", "decision_time", "status", "reason_code", "duration_ms"):
            if hasattr(record, field): payload[field] = getattr(record, field)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def get_logger() -> logging.Logger:
    logger = logging.getLogger("quant_pipeline.p8.s5")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
