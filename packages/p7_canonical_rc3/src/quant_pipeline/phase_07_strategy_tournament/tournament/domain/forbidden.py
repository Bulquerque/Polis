from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import TemporalViolation
from .reasoning import reason_prefix


def scan_forbidden_fields(value: Any, forbidden: set[str], *, module_id: str, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in forbidden:
                raise TemporalViolation(
                    f"{reason_prefix(module_id)}_FORBIDDEN_FIELD_DETECTED",
                    "forbidden outcome or future field detected",
                    module_id=module_id,
                    details={"field": key_text, "path": child_path},
                )
            scan_forbidden_fields(child, forbidden, module_id=module_id, path=child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            scan_forbidden_fields(child, forbidden, module_id=module_id, path=f"{path}[{index}]")
