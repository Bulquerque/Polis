"""Minimal offline CLI for deterministic P6 Wave 1 execution."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .orchestration.phase_runner import run_phase


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="p6",
        description="Run P6 strategy synthesis from JSON inputs",
    )
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--configuration", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_phase(
        json.loads(args.inputs.read_text(encoding="utf-8")),
        json.loads(args.configuration.read_text(encoding="utf-8")),
    )
    payload = _jsonable(result)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    return 0


def _jsonable(value: Any) -> Any:
    """Convert public runtime results to deterministic JSON-compatible data."""
    if isinstance(value, BaseModel):
        return {
            name: _jsonable(getattr(value, name))
            for name in value.__class__.model_fields
            if not name.startswith("_")
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
