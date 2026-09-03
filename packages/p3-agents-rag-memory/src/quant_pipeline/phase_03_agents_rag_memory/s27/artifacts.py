"""Artifact construction helpers for P3.S27."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel

from .common import lineage_id

T = TypeVar("T", bound=BaseModel)


def artifact_kwargs(*, module_id: str, output_name: str, schema_version: str, run_id: str, cycle_id: int, as_of_time: datetime, lineages: Iterable[str]) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_of_time,
        "lineage_id": lineage_id(module_id, output_name, lineages),
    }
