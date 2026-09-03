from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml

from .errors import S4ContractError
from ...shared.assets import source_or_packaged_root


class SchemaRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, relative: str) -> dict[str, Any]:
        if relative not in self._cache:
            path = self._root / relative
            if not path.is_file():
                raise S4ContractError(
                    "P3_S4_SCHEMA_NOT_FOUND",
                    f"schema not found: {path}",
                )
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise S4ContractError(
                    "P3_S4_SCHEMA_INVALID",
                    f"{relative} is not a mapping",
                )
            Draft202012Validator.check_schema(value)
            self._cache[relative] = value
        return self._cache[relative]

    def validate(
        self,
        relative: str,
        value: Any,
        *,
        label: str,
    ) -> None:
        validator = Draft202012Validator(
            self.load(relative),
            format_checker=FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: list(error.path),
        )
        if errors:
            message = "; ".join(
                f"{'.'.join(map(str, error.path)) or '$'}: "
                f"{error.message}"
                for error in errors[:5]
            )
            raise S4ContractError(
                "P3_S4_SCHEMA_VIOLATION",
                f"{label}: {message}",
            )


def package_root() -> Path:
    return source_or_packaged_root()


def resolve_schema_document(
    schema_path: str,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    config = config or {}
    documents = config.get("schema_documents")
    if isinstance(documents, dict) and schema_path in documents:
        value = documents[schema_path]
        if not isinstance(value, dict):
            raise S4ContractError(
                "P3_S4_SCHEMA_INVALID",
                f"injected schema {schema_path} is not a mapping",
            )
        Draft202012Validator.check_schema(value)
        return value

    root_value = config.get("schema_root")
    root = Path(root_value) if root_value is not None else package_root()
    path = root / schema_path
    if not path.is_file():
        raise S4ContractError(
            "P3_S4_SCHEMA_NOT_FOUND",
            f"schema not found: {path}",
        )
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S4ContractError(
            "P3_S4_SCHEMA_INVALID",
            f"schema {path} is not a mapping",
        )
    Draft202012Validator.check_schema(value)
    return value
