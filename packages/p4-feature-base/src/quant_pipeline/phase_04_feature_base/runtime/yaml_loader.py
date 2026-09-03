from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import yaml


class TextResource(Protocol):
    def read_text(self, encoding: str = "utf-8") -> str: ...

    def is_file(self) -> bool: ...


def load_yaml(path: str | Path | TextResource) -> dict[str, Any]:
    """Load a YAML mapping with SafeLoader and reject non-mapping roots."""
    if isinstance(path, (str, Path)):
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"missing YAML file: {source}")
        text = source.read_text(encoding="utf-8")
        label = str(source)
    else:
        text = path.read_text(encoding="utf-8")
        label = str(path)
    value = yaml.safe_load(text)
    if not isinstance(value, Mapping):
        raise ValueError(f"YAML root must be a mapping: {label}")
    return dict(value)
