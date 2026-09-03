from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
import json
from math import fsum
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from ...s30_models import (
    AgentDisagreementPanel,
    AgentDisagreementRecord,
    ArtifactManifestEntry,
    BeliefOutcomeCommitmentLog,
    ConsumerBindingStatus,
    ContextMemoryFeaturePanel,
    ContextMemoryFeatureRecord,
    EvidenceRelation,
    EvidenceTagPanel,
    EvidenceTagRecord,
    ExecutionContext,
    FeatureProjectionConfig,
    FeatureType,
    HypothesisRecord,
    HypothesisRegistry,
    MemoryRecord,
    NextMemoryState,
    Phase3RunSnapshot,
    Phase4SocialHandoffManifest,
    PrivacyClass,
    ProjectionDefinition,
    PropositionDefinition,
    PropositionRegistryConfig,
    QualityStatus,
    SocialFeaturePanel,
    SocialFeatureRecord,
    SocietyStateRecord,
    ValidatedSocietyStatePanel,
    VariableEvolutionInputManifest,
)

T = TypeVar("T")

FORBIDDEN_FIELDS = frozenset(
    {
        "target",
        "future_return",
        "prediction",
        "signal_direction",
        "candidate_id",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
        "realized_pnl",
        "feature_genome",
        "mutation_candidate",
        "promotion_decision",
    }
)
PRIVATE_FIELDS = frozenset(
    {
        "content",
        "memory_text",
        "message_text",
        "prompt",
        "raw_payload",
        "tool_payload",
        "private_notes",
        "credentials",
        "api_key",
    }
)


class S30Error(ValueError):
    """Base error for deterministic S30 failures."""


class S30ContractError(S30Error):
    """Raised when an S30 input or output contract is violated."""


class S30TemporalError(S30ContractError):
    """Raised when point-in-time semantics are violated."""


class S30LineageError(S30ContractError):
    """Raised when an artifact cannot be traced to declared inputs."""


class S30PrivacyError(S30ContractError):
    """Raised when private memory or tool content crosses the projection boundary."""


class S30IntegrityError(S30ContractError):
    """Raised when hashes or atomic handoff expectations do not match."""


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _artifact_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{_digest(value)[:20]}"


def _lineage_id(prefix: str, value: Any) -> str:
    return f"lineage-{prefix}-{_digest(value)[:24]}"


def _round(value: float, precision: int) -> float:
    return round(float(value), precision)


def _scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                raise S30ContractError(f"forbidden field detected at {path}.{key_text}")
            if key_text in PRIVATE_FIELDS:
                raise S30PrivacyError(f"private field detected at {path}.{key_text}")
            _scan_forbidden(child, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")


def _parse(model: type[T], value: Any, name: str) -> T:
    try:
        if isinstance(value, BaseModel):
            return model.model_validate(value, strict=True)  # type: ignore[attr-defined, no-any-return]
        blob = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return model.model_validate_json(blob, strict=True)  # type: ignore[attr-defined, no-any-return]
    except (ValidationError, TypeError, ValueError) as exc:
        raise S30ContractError(f"{name} failed strict validation: {exc}") from exc


def _unique_index(
    records: Iterable[T],
    key: Callable[[T], Any],
    name: str,
) -> dict[Any, T]:
    result: dict[Any, T] = {}
    for record in records:
        record_key = key(record)
        if record_key in result:
            raise S30ContractError(f"duplicate {name} key: {record_key!r}")
        result[record_key] = record
    return result


def _quality_rollup(statuses: Sequence[QualityStatus]) -> QualityStatus:
    if any(status == QualityStatus.BLOCKED for status in statuses):
        return QualityStatus.BLOCKED
    if any(status == QualityStatus.DEGRADED for status in statuses):
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def _validate_artifact_alignment(
    context: ExecutionContext,
    artifacts: Sequence[Any],
) -> None:
    for artifact in artifacts:
        for field in ("run_id", "cycle_id", "pipeline_version"):
            if getattr(artifact, field) != getattr(context, field):
                raise S30ContractError(
                    f"{artifact.__class__.__name__}.{field} does not match execution context"
                )
        if artifact.as_of_time != context.as_of_time:
            raise S30TemporalError(
                f"{artifact.__class__.__name__}.as_of_time does not match execution context"
            )
        if artifact.created_at < artifact.as_of_time:
            raise S30TemporalError(
                f"{artifact.__class__.__name__}.created_at is before its as_of_time"
            )


def _module_result(
    module_id: str,
    module_name: str,
    output_name: str,
    output: BaseModel,
    started_at: float,
) -> dict[str, Any]:
    payload = output.model_dump(mode="json")
    records = payload.get("records", [])
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "phase_03_agents_rag_memory",
        "subphase": "P3.S30",
        "implementation_status": "IMPLEMENTED_QUALIFIED_INTERNAL",
        "outputs": {output_name: payload},
        "observability": {
            "events": ("module_started", "input_contract_validated", "module_succeeded"),
            "duration_ms": round((perf_counter() - started_at) * 1000.0, 6),
            "output_record_count": len(records) if isinstance(records, list) else 1,
            "warning_count": len(payload.get("quality_reasons", [])),
            "error_count": 0,
        },
    }


def _evidence_summary(
    records: Sequence[EvidenceTagRecord],
) -> dict[str, float]:
    if not records:
        return {
            "evidence_count": 0.0,
            "mean_source_quality": 0.0,
            "support_share": 0.0,
            "opposition_share": 0.0,
            "context_share": 0.0,
        }
    count = len(records)
    relation_counts = defaultdict(int)
    for record in records:
        relation_counts[record.evidence_relation] += 1
    return {
        "evidence_count": float(count),
        "mean_source_quality": fsum(record.source_quality_score for record in records) / count,
        "support_share": relation_counts[EvidenceRelation.SUPPORTS] / count,
        "opposition_share": relation_counts[EvidenceRelation.OPPOSES] / count,
        "context_share": relation_counts[EvidenceRelation.CONTEXT_ONLY] / count,
    }


def _projection_value(
    definition: ProjectionDefinition,
    society: SocietyStateRecord,
    disagreement: AgentDisagreementRecord,
    evidence_summary: Mapping[str, float],
) -> float | None:
    if definition.source == "society":
        value = getattr(society, definition.source_field, None)
    elif definition.source == "disagreement":
        value = getattr(disagreement, definition.source_field, None)
    elif definition.source == "evidence":
        value = evidence_summary.get(definition.source_field)
    else:
        raise S30ContractError(
            f"social projection does not accept source={definition.source!r}"
        )
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise S30ContractError(
            f"feature {definition.feature_id!r} source field is not numeric"
        )
    return float(value)
