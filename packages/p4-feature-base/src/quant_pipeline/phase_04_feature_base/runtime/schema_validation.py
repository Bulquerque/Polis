from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import CompatibilityMode
from .yaml_loader import TextResource, load_yaml


def validate_json_schema(instance: Any, schema: Mapping[str, Any], context: str) -> None:
    """Validate an instance against a checked Draft 2020-12 schema."""
    try:
        validator = _checked_validator(_schema_key(schema))
    except SchemaError as exc:
        raise BoundaryContractError(
            BoundaryErrorCode.SCHEMA_INVALID,
            f"invalid schema definition: {exc.message}",
            path=context,
        ) from exc
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    first = errors[0]
    suffix = ".".join(str(part) for part in first.absolute_path)
    path = f"{context}.{suffix}" if suffix else context
    raise BoundaryContractError(
        BoundaryErrorCode.SCHEMA_INVALID,
        first.message,
        path=path,
    )


def _schema_key(schema: Mapping[str, Any]) -> str:
    """Create a deterministic cache key from schema content, not identity."""
    return json.dumps(dict(schema), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@lru_cache(maxsize=128)
def _checked_validator(schema_key: str) -> Draft202012Validator:
    schema_dict = json.loads(schema_key)
    Draft202012Validator.check_schema(schema_dict)
    return Draft202012Validator(schema_dict, format_checker=_format_checker())


def _validation_cache_clear() -> None:
    """Clear cached schema validators for tests and long-running reloads."""
    _checked_validator.cache_clear()


def _format_checker() -> FormatChecker:
    """Build a stable RFC3339 checker across jsonschema releases.

    jsonschema has changed which built-in format names are registered between
    releases.  Registering the four formats used by P4 locally avoids a
    dependency-version failure and treats nullable temporal fields according to
    JSON Schema semantics: ``format`` constrains a value when present, not null.
    """
    checker = FormatChecker()

    @checker.checks("date-time", raises=(TypeError, ValueError, OverflowError))
    def _date_time(value: Any) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None

    @checker.checks("date", raises=(TypeError, ValueError, OverflowError))
    def _date(value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, str) and date.fromisoformat(value) is not None

    @checker.checks("time", raises=(TypeError, ValueError, OverflowError))
    def _time(value: Any) -> bool:
        if value is None:
            return True
        return (
            isinstance(value, str)
            and time.fromisoformat(value.replace("Z", "+00:00")) is not None
        )

    @checker.checks("duration", raises=(TypeError, ValueError, OverflowError))
    def _duration(value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, str) and bool(
            re.fullmatch(
                r"P(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?",
                value,
            )
        )

    return checker


def load_schema(path: str | Path | TextResource) -> dict[str, Any]:
    return load_yaml(path)


def validate_legacy_upstream_schema(
    artifact_name: str,
    artifact: Mapping[str, Any],
    schema: Mapping[str, Any],
    mode: CompatibilityMode,
) -> tuple[str, ...]:
    """Validate the compact schema dialect used by the RC4.1 upstream phases."""
    warnings: list[str] = []
    expected = schema.get("artifact") or schema.get("artifact_name")
    if expected and str(expected) != artifact_name:
        raise BoundaryContractError(
            BoundaryErrorCode.SCHEMA_INVALID,
            f"schema artifact mismatch: expected {expected!r}",
            path=artifact_name,
        )
    required = [str(field) for field in schema.get("required_fields", [])]
    records = artifact.get("records")
    panel_schema = isinstance(records, list) and any(
        field not in artifact for field in required
    )
    if panel_schema:
        _validate_legacy_records(artifact_name, records, required, artifact, mode, warnings)
    else:
        missing = [field for field in required if field not in artifact]
        if missing:
            raise BoundaryContractError(
                BoundaryErrorCode.SCHEMA_INVALID,
                f"missing fields {missing}",
                path=artifact_name,
            )
    return tuple(warnings)


def _validate_legacy_records(
    artifact_name: str,
    records: list[Any],
    required: list[str],
    artifact: Mapping[str, Any],
    mode: CompatibilityMode,
    warnings: list[str],
) -> None:
    ignored_top_level_fields = {"artifact_id", "created_at"}
    for index, record in enumerate(records):
        record_path = f"{artifact_name}.records[{index}]"
        if not isinstance(record, Mapping):
            raise BoundaryContractError(
                BoundaryErrorCode.SCHEMA_INVALID,
                "record must be an object",
                path=record_path,
            )
        missing = [
            field
            for field in required
            if field not in record
            and field not in artifact
            and field not in ignored_top_level_fields
        ]
        if not missing:
            continue
        message = f"legacy record missing fields {missing}"
        if mode is CompatibilityMode.STRICT:
            raise BoundaryContractError(
                BoundaryErrorCode.SCHEMA_INVALID,
                message,
                path=record_path,
            )
        warnings.append(f"record[{index}]: {message}")
