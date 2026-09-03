from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope, build_artifact
from ...boundary.records import RankingPolicyRecord
from ...domain.errors import ContractViolation
from ...domain.serialization import sha256_hex


def single_policy(artifact: ArtifactEnvelope[RankingPolicyRecord], *, module_id: str) -> RankingPolicyRecord:
    if len(artifact.records) != 1:
        raise ContractViolation(
            "P7_S3_POLICY_RECORD_COUNT_INVALID",
            "ranking_policy_context must contain exactly one record",
            module_id=module_id,
        )
    return artifact.records[0]


def unique_by(items: Iterable[Any], key: Any, *, code: str, module_id: str) -> dict[Any, Any]:
    output: dict[Any, Any] = {}
    duplicates: list[Any] = []
    for item in items:
        item_key = key(item)
        if item_key in output:
            duplicates.append(item_key)
        else:
            output[item_key] = item
    if duplicates:
        raise ContractViolation(
            code,
            "duplicate records violate artifact grain",
            module_id=module_id,
            details={"duplicates": sorted(str(value) for value in duplicates)},
        )
    return output


def output_lineage(module_id: str, input_artifacts: Iterable[ArtifactEnvelope[Any]]) -> str:
    return sha256_hex(
        {
            "module_id": module_id,
            "input_artifacts": sorted(
                (artifact.artifact_name, artifact.artifact_id, artifact.content_sha256)
                for artifact in input_artifacts
            ),
        }
    )


def build_outputs(
    *,
    module_id: str,
    base: ArtifactEnvelope[Any],
    execution_time: datetime,
    lineage_id: str,
    named_records: dict[str, tuple[Any, ...]],
) -> dict[str, ArtifactEnvelope[Any]]:
    return {
        name: build_artifact(
            artifact_name=name,
            schema_version="1.0.0",
            producer_module_id=module_id,
            run_id=base.run_id,
            cycle_id=base.cycle_id,
            decision_time=base.decision_time,
            execution_time=execution_time,
            available_at=base.available_at,
            lineage_id=lineage_id,
            records=records,
        )
        for name, records in named_records.items()
    }


def reason_counts(values: Iterable[str | None]) -> dict[str, int]:
    return dict(sorted(Counter(value for value in values if value).items()))
