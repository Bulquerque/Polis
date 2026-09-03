from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .artifacts import ArtifactEnvelope, ExecutionContext
from .errors import P4S7Error


FORBIDDEN_FIELDS = {
    "target", "label", "future_return", "future_volatility", "prediction",
    "signal_direction", "candidate_id", "candidate_score", "rank_score",
    "portfolio_weight", "trade_decision", "realized_pnl", "execution_fill",
}


def require_artifacts(
    inputs: Mapping[str, ArtifactEnvelope], required: Iterable[str], module_id: str
) -> None:
    missing = sorted(set(required) - set(inputs))
    if missing:
        raise P4S7Error(f"{module_id.replace('.', '_')}_INPUT_INVALID", f"missing {missing}")
    mismatches = sorted(name for name in required if inputs[name].artifact_name != name)
    if mismatches:
        raise P4S7Error(
            f"{module_id.replace('.', '_')}_INPUT_INVALID",
            f"mapping keys do not match artifact_name: {mismatches}",
        )


def reject_forbidden_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in FORBIDDEN_FIELDS:
                raise P4S7Error("P4_S7_FORBIDDEN_FIELD", f"{path}.{key}")
            reject_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_forbidden_fields(child, f"{path}[{index}]")


def validate_context(artifact: ArtifactEnvelope, context: ExecutionContext) -> None:
    try:
        artifact.verify_integrity()
    except ValueError as exc:
        raise P4S7Error("P4_S7_HASH_MISMATCH", artifact.artifact_name) from exc
    if artifact.execution_status == "BLOCKED" or artifact.quality_status == "BLOCKED":
        raise P4S7Error("P4_S7_UPSTREAM_BLOCKED", artifact.artifact_name)
    if artifact.run_id != context.run_id or artifact.cycle_id != context.cycle_id:
        raise P4S7Error("P4_S7_CONTEXT_MISMATCH", artifact.artifact_name)
    if artifact.as_of_time != context.as_of_time:
        raise P4S7Error("P4_S7_AS_OF_MISMATCH", artifact.artifact_name)
    reject_forbidden_fields(artifact.records)
    reject_forbidden_fields(artifact.metadata)
