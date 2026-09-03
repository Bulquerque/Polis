"""Optional PyArrow codec isolated behind the Parquet project extra."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import TypeVar

from pydantic import BaseModel

from ..errors import ErrorCategory, PersistenceFailureError, error
from .....shared.optional_dependencies import OptionalDependencyUnavailableError, require_dependency

T = TypeVar("T", bound=BaseModel)


def encode_parquet(records: Sequence[BaseModel]) -> bytes:
    """Serialize models to Parquet without importing PyArrow during core import."""

    try:
        pyarrow = require_dependency("pyarrow", extra="parquet", purpose="Parquet graph serialization")
        parquet = require_dependency("pyarrow.parquet", extra="parquet", purpose="Parquet graph serialization")
    except OptionalDependencyUnavailableError as exc:
        raise PersistenceFailureError(
            error(
                "P3_S13_PARQUET_DEPENDENCY_MISSING",
                ErrorCategory.PERSISTENCE,
                "record_format PARQUET requires the optional pyarrow dependency",
            )
        ) from exc
    table = pyarrow.Table.from_pylist([record.model_dump(mode="json") for record in records])
    sink = pyarrow.BufferOutputStream()
    parquet.write_table(table, sink)
    return sink.getvalue().to_pybytes()


def decode_parquet(content: bytes, model: type[T]) -> tuple[T, ...]:
    """Deserialize Parquet rows into the requested strict model type."""

    try:
        parquet = require_dependency("pyarrow.parquet", extra="parquet", purpose="Parquet graph deserialization")
    except OptionalDependencyUnavailableError as exc:
        raise PersistenceFailureError(
            error(
                "P3_S13_PARQUET_DEPENDENCY_MISSING",
                ErrorCategory.PERSISTENCE,
                "reading Parquet requires the optional pyarrow dependency",
            )
        ) from exc
    table = parquet.read_table(BytesIO(content))
    return tuple(model.model_validate(row, strict=False) for row in table.to_pylist())
