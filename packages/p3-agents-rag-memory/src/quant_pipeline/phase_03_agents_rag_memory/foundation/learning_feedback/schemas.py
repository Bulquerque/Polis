from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml

from .errors import S3ContractError


class SchemaRegistry:
    """Load and validate local Draft 2020-12 schemas with a small cache."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, relative: str) -> dict[str, Any]:
        if relative in self._cache:
            return self._cache[relative]

        path = self._root / relative
        if not path.is_file() and relative.startswith(
            ("schemas/internal/", "schemas/extensions/")
        ):
            # Full-package integration flattens internal/extension schemas into schemas/.
            path = self._root / "schemas" / Path(relative).name
        if not path.is_file():
            raise S3ContractError(
                "P3_S3_SCHEMA_NOT_FOUND",
                f"schema not found: {relative}",
            )

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise S3ContractError(
                "P3_S3_SCHEMA_INVALID",
                f"{relative} is not a mapping",
            )

        try:
            Draft202012Validator.check_schema(value)
        except Exception as exc:
            raise S3ContractError(
                "P3_S3_SCHEMA_INVALID",
                f"{relative} is not valid Draft 2020-12",
            ) from exc

        self._cache[relative] = value
        return value

    def validate(self, relative: str, value: Any, *, label: str) -> None:
        validator = Draft202012Validator(
            self.load(relative),
            format_checker=FormatChecker(),
        )
        errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
        if not errors:
            return

        message = "; ".join(
            f"{'.'.join(map(str, error.path)) or '$'}: {error.message}"
            for error in errors[:5]
        )
        raise S3ContractError(
            "P3_S3_SCHEMA_VIOLATION",
            f"{label}: {message}",
        )
