from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import yaml

from .errors import S2ContractError
from ...shared.assets import source_or_packaged_root


PACKAGE_ROOT = source_or_packaged_root()
DEPENDENCY_SCHEMA_ROOT = PACKAGE_ROOT / "schemas" / "dependencies"
EXTERNAL_SCHEMA_ROOT = PACKAGE_ROOT / "schemas" / "external"
INTERNAL_SCHEMA_ROOT = PACKAGE_ROOT / "schemas" / "internal"
CANONICAL_SCHEMA_ROOT = PACKAGE_ROOT / "schemas"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise S2ContractError("P3_S2_SCHEMA_MISSING", f"Missing schema: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise S2ContractError("P3_S2_SCHEMA_INVALID", f"Schema must be a mapping: {path}")
    return value


class SchemaRegistry:
    def _resolve(self, root: Path, name: str) -> Path:
        standalone = root / f"{name}.schema.yaml"
        canonical = CANONICAL_SCHEMA_ROOT / f"{name}.schema.yaml"
        path = standalone if standalone.is_file() else canonical
        if not path.is_file():
            raise S2ContractError("P3_S2_SCHEMA_MISSING", f"Missing schema for {name}")
        return path

    def dependency(self, name: str) -> dict[str, Any]:
        return load_yaml(self._resolve(DEPENDENCY_SCHEMA_ROOT, name))

    def external(self, name: str) -> dict[str, Any]:
        return load_yaml(self._resolve(EXTERNAL_SCHEMA_ROOT, name))

    def internal(self, name: str) -> dict[str, Any]:
        return load_yaml(self._resolve(INTERNAL_SCHEMA_ROOT, name))

    def validate(self, schema: dict[str, Any], value: Any, *, name: str) -> None:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
        if errors:
            details = [
                f"{'/'.join(str(part) for part in error.path) or '$'}: {error.message}"
                for error in errors[:10]
            ]
            raise S2ContractError(
                "P3_S2_SCHEMA_VALIDATION_FAILED",
                f"{name} failed JSON Schema validation: {details}",
            )

    def validate_dependency(self, name: str, value: Any) -> None:
        self.validate(self.dependency(name), value, name=name)

    def validate_external(self, name: str, value: Any) -> None:
        schema = self.external(name)
        required = tuple(schema.get("required_fields", ()))
        if required:
            if not isinstance(value, dict):
                raise S2ContractError(
                    "P3_S2_EXTERNAL_SCHEMA_INVALID",
                    f"{name} must be a mapping",
                )
            missing = [field for field in required if field not in value or value[field] is None]
            if missing:
                raise S2ContractError(
                    "P3_S2_EXTERNAL_REQUIRED_FIELD_MISSING",
                    f"{name} is missing external fields: {missing}",
                )

    def validate_internal(self, name: str, value: Any) -> None:
        self.validate(self.internal(name), value, name=name)
