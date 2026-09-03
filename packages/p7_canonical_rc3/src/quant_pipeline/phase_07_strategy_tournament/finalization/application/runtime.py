"""Shared module runtime helpers."""
from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import Iterable, Mapping

from pydantic import BaseModel

from ..artifacts import build_artifact
from ..boundary.base import ArtifactEnvelope, ModuleReceipt
from ..boundary.config import RuntimeConfig


class Timer:
    def __init__(self) -> None:
        self._start = perf_counter()

    def elapsed_ms(self) -> float:
        return (perf_counter() - self._start) * 1000.0


def artifact_from_records(
    *,
    name: str,
    schema_version: str,
    module_id: str,
    runtime: RuntimeConfig,
    cycle_id: str,
    decision_time,
    lineage_id: str,
    records: Iterable[BaseModel],
) -> ArtifactEnvelope:
    return build_artifact(
        artifact_name=name,
        schema_version=schema_version,
        producer_module_id=module_id,
        run_id=runtime.run_id,
        cycle_id=cycle_id,
        decision_time=decision_time,
        available_at=decision_time,
        created_at=runtime.run_timestamp,
        lineage_id=lineage_id,
        records=records,
    )


def receipt(
    *,
    module_id: str,
    runtime: RuntimeConfig,
    cycle_id: str,
    inputs: Iterable[ArtifactEnvelope],
    outputs: Iterable[ArtifactEnvelope],
    counts: Mapping[str, int],
    reason_codes: Iterable[str],
    policy_versions: Mapping[str, str],
    timer: Timer,
) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        trace_id=runtime.trace_id,
        run_id=runtime.run_id,
        cycle_id=cycle_id,
        status="PASS",
        input_artifact_ids=tuple(sorted(item.artifact_id for item in inputs)),
        output_artifact_ids=tuple(sorted(item.artifact_id for item in outputs)),
        counts=dict(counts),
        reason_code_distribution=dict(Counter(reason_codes)),
        policy_versions=dict(policy_versions),
        duration_ms=timer.elapsed_ms(),
    )
