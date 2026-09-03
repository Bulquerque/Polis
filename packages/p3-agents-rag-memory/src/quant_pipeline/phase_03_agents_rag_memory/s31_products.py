from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from time import perf_counter
from typing import Any, Mapping, Sequence, TypeVar

from pydantic import BaseModel, ValidationError

from .s31_models import (
    ArtifactReference,
    BeliefOutcomeCommitmentLog,
    BlindHoldoutPolicy,
    CommitmentMaturityEntry,
    ConsumerBindingStatus,
    CutoffRiskClass,
    EvaluationReadiness,
    ExecutionContext,
    ModelKnowledgeCutoffReport,
    P9ConsumerCompatibilityConfig,
    P9ContextLearningHandoffManifest,
    P9EvaluationEvidenceBundle,
    Phase3RunSnapshot,
    Phase4SocialHandoffManifest,
    QualityStatus,
    ReproducibilityKeys,
    ValidatedSocietyStatePanel,
    VariableEvolutionInputManifest,
)

T = TypeVar("T")

FORBIDDEN_FIELDS = frozenset(
    {
        "future_return",
        "realized_return",
        "realized_pnl",
        "outcome_value",
        "outcome_label",
        "target",
        "label",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
        "sharpe",
        "sortino",
        "calmar",
        "bootstrap_result",
        "robustness_score",
        "promotion_decision",
        "next_cycle_decision",
        "evaluation_results",
        "evaluation_metrics",
    }
)


class S31Error(ValueError):
    """Base error for deterministic S31 export failures."""


class S31ContractError(S31Error):
    """Raised when an input or output contract is invalid."""


class S31TemporalError(S31ContractError):
    """Raised when point-in-time or maturity semantics are violated."""


class S31IntegrityError(S31ContractError):
    """Raised when a hash, reference, or lineage expectation is violated."""


class S31AuthorityError(S31ContractError):
    """Raised when S31 attempts to absorb P9 evaluation authority."""


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




def _artifact_content_hash(name: str, value: BaseModel) -> str:
    payload = value.model_dump(mode="json")
    if name == "phase4_social_handoff_manifest":
        payload["entries"] = sorted(payload["entries"], key=lambda row: row["artifact_name"])
    elif name == "belief_outcome_commitment_log":
        payload["records"] = sorted(payload["records"], key=lambda row: row["commitment_id"])
    elif name == "validated_society_state_panel":
        payload["records"] = sorted(
            payload["records"],
            key=lambda row: (
                row["underlying_id"],
                row["proposition_id"],
                row["horizon"],
                row["as_of_time"],
            ),
        )
    return _digest(payload)

def _artifact_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{_digest(value)[:20]}"


def _lineage_id(prefix: str, value: Any) -> str:
    return f"lineage-{prefix}-{_digest(value)[:24]}"


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
        raise S31ContractError(f"{name} failed strict validation: {exc}") from exc


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise S31ContractError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise S31ContractError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                raise S31AuthorityError(f"forbidden evaluation field detected at {path}.{key_text}")
            _scan_forbidden(child, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")


def _quality_rollup(statuses: Sequence[QualityStatus]) -> QualityStatus:
    if any(status == QualityStatus.BLOCKED for status in statuses):
        return QualityStatus.BLOCKED
    if any(status == QualityStatus.DEGRADED for status in statuses):
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def _cutoff_quality(risk: CutoffRiskClass) -> QualityStatus:
    if risk == CutoffRiskClass.CONTAMINATION_RISK:
        return QualityStatus.BLOCKED
    if risk == CutoffRiskClass.UNKNOWN:
        return QualityStatus.DEGRADED
    return QualityStatus.PASS


def _module_result(
    module_id: str,
    module_name: str,
    output_name: str,
    output: BaseModel,
    started_at: float,
) -> dict[str, Any]:
    payload = output.model_dump(mode="json")
    items = payload.get("items", payload.get("artifact_hashes", {}))
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "phase_03_agents_rag_memory",
        "subphase": "P3.S31",
        "implementation_status": "IMPLEMENTED_QUALIFIED_INTERNAL",
        "outputs": {output_name: payload},
        "observability": {
            "events": ("module_started", "input_contract_validated", "module_succeeded"),
            "duration_ms": round((perf_counter() - started_at) * 1000.0, 6),
            "output_record_count": len(items),
            "warning_count": len(payload.get("quality_reasons", [])),
            "error_count": 0,
        },
    }


def _validate_common_alignment(
    context: ExecutionContext,
    phase4: Phase4SocialHandoffManifest,
    commitments: BeliefOutcomeCommitmentLog,
    snapshot: Phase3RunSnapshot,
    society: ValidatedSocietyStatePanel,
    variable: VariableEvolutionInputManifest,
) -> None:
    artifacts = (phase4, commitments, society)
    for artifact in artifacts:
        for field in ("run_id", "cycle_id", "pipeline_version"):
            if getattr(artifact, field) != getattr(context, field):
                raise S31ContractError(
                    f"{artifact.__class__.__name__}.{field} does not match execution context"
                )
        if artifact.as_of_time != context.as_of_time:
            raise S31TemporalError(
                f"{artifact.__class__.__name__}.as_of_time does not match execution context"
            )
        if artifact.created_at > context.created_at:
            raise S31TemporalError(
                f"{artifact.__class__.__name__}.created_at is after export created_at"
            )
    for field in ("run_id", "cycle_id", "pipeline_version"):
        if getattr(snapshot, field) != getattr(context, field):
            raise S31ContractError(f"Phase3RunSnapshot.{field} does not match execution context")
    if snapshot.as_of_time != context.as_of_time:
        raise S31TemporalError("Phase3RunSnapshot.as_of_time does not match execution context")
    variable_as_of = _parse_datetime(variable.as_of_time, "variable_evolution_input_manifest.as_of_time")
    if variable_as_of != context.as_of_time:
        raise S31TemporalError("VariableEvolutionInputManifest.as_of_time does not match execution context")
    if variable.canonical_society_state_ref != society.artifact_id:
        raise S31IntegrityError("variable evolution society-state reference does not match input artifact")
    if variable.belief_commitment_ref != commitments.artifact_id:
        raise S31IntegrityError("variable evolution commitment reference does not match input artifact")
    phase4_entries = {entry.artifact_name: entry.artifact_id for entry in phase4.entries}
    expected_refs = {
        "social_feature_panel": variable.social_feature_ref,
        "context_memory_feature_panel": variable.context_memory_feature_ref,
        "hypothesis_registry": variable.hypothesis_registry_ref,
    }
    for name, artifact_id in expected_refs.items():
        if phase4_entries.get(name) != artifact_id:
            raise S31IntegrityError(f"variable evolution reference does not match phase4 entry: {name}")


def _artifact_references(
    context: ExecutionContext,
    phase4: Phase4SocialHandoffManifest,
    variable: VariableEvolutionInputManifest,
    commitments: BeliefOutcomeCommitmentLog,
    cutoff: ModelKnowledgeCutoffReport,
    snapshot: Phase3RunSnapshot,
    society: ValidatedSocietyStatePanel,
) -> tuple[ArtifactReference, ...]:
    society_status = _quality_rollup([record.quality_status for record in society.records])
    if not society.records:
        society_status = QualityStatus.DEGRADED
    commitment_status = QualityStatus.PASS if commitments.records else QualityStatus.DEGRADED
    rows = [
        ArtifactReference(
            artifact_name="phase4_social_handoff_manifest",
            artifact_id=phase4.artifact_id,
            schema_id=phase4.schema_id,
            schema_version=phase4.schema_version,
            content_hash=_artifact_content_hash("phase4_social_handoff_manifest", phase4),
            row_count=len(phase4.entries),
            grain=("artifact_name",),
            producer_module_id="P3.S30.M04",
            lineage_id=phase4.lineage_id,
            available_at=phase4.created_at,
            quality_status=phase4.quality_status,
        ),
        ArtifactReference(
            artifact_name="variable_evolution_input_manifest",
            artifact_id=variable.manifest_id,
            schema_id="p3.s30.variable_evolution_input_manifest.semantic",
            schema_version="1.0.0",
            content_hash=_digest(variable),
            row_count=1,
            grain=("manifest_id",),
            producer_module_id="P3.S30.M05",
            lineage_id=variable.lineage_id,
            available_at=context.created_at,
            quality_status=QualityStatus.PASS,
        ),
        ArtifactReference(
            artifact_name="belief_outcome_commitment_log",
            artifact_id=commitments.artifact_id,
            schema_id="p3.s30.belief_outcome_commitment_log.input",
            schema_version="1.0.0",
            content_hash=_artifact_content_hash("belief_outcome_commitment_log", commitments),
            row_count=len(commitments.records),
            grain=("commitment_id",),
            producer_module_id="P3.S22.M03",
            lineage_id=commitments.lineage_id,
            available_at=commitments.created_at,
            quality_status=commitment_status,
        ),
        ArtifactReference(
            artifact_name="model_knowledge_cutoff_report",
            artifact_id=_artifact_id("model-knowledge-cutoff-report", cutoff),
            schema_id="p3.s31.model_knowledge_cutoff_report.input",
            schema_version="1.0.0",
            content_hash=_digest(cutoff),
            row_count=1,
            grain=("provider_id", "model_id", "model_version"),
            producer_module_id="P3.S2.M03",
            lineage_id=cutoff.lineage_id,
            available_at=context.created_at,
            quality_status=_cutoff_quality(cutoff.risk_class),
        ),
        ArtifactReference(
            artifact_name="phase3_run_snapshot",
            artifact_id=snapshot.snapshot_id,
            schema_id="p3.s30.phase3_run_snapshot.input",
            schema_version="1.0.0",
            content_hash=_digest(snapshot),
            row_count=1,
            grain=("snapshot_id",),
            producer_module_id="P3.S2.M02",
            lineage_id=snapshot.lineage_id,
            available_at=context.created_at,
            quality_status=QualityStatus.PASS,
        ),
        ArtifactReference(
            artifact_name="validated_society_state_panel",
            artifact_id=society.artifact_id,
            schema_id="p3.s30.validated_society_state_panel.input",
            schema_version="1.0.0",
            content_hash=_artifact_content_hash("validated_society_state_panel", society),
            row_count=len(society.records),
            grain=("underlying_id", "proposition_id", "horizon", "as_of_time"),
            producer_module_id="P3.S28.M03",
            lineage_id=society.lineage_id,
            available_at=society.created_at,
            quality_status=society_status,
        ),
    ]
    return tuple(sorted(rows, key=lambda item: item.artifact_name))


def _commitment_schedule(
    commitments: BeliefOutcomeCommitmentLog,
    context: ExecutionContext,
) -> tuple[CommitmentMaturityEntry, ...]:
    result = []
    for record in sorted(commitments.records, key=lambda item: item.commitment_id):
        if record.committed_at > context.as_of_time:
            raise S31TemporalError(
                f"commitment {record.commitment_id!r} was created after run as_of_time"
            )
        readiness = (
            EvaluationReadiness.READY_FOR_EVALUATION
            if record.matures_at <= context.created_at
            else EvaluationReadiness.PENDING_MATURITY
        )
        result.append(
            CommitmentMaturityEntry(
                commitment_id=record.commitment_id,
                commitment_hash=record.commitment_hash,
                person_id=record.person_id,
                underlying_id=record.underlying_id,
                proposition_id=record.proposition_id,
                horizon=record.horizon,
                belief_value=record.belief_value,
                confidence=record.confidence,
                evidence_refs=record.evidence_refs,
                committed_at=record.committed_at,
                matures_at=record.matures_at,
                readiness=readiness,
                lineage_id=record.lineage_id,
            )
        )
    return tuple(result)


def build_p9_evaluation_evidence_bundle(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a reproducible, outcome-blind evidence bundle for future P9 evaluation."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "phase4_social_handoff_manifest",
        "variable_evolution_input_manifest",
        "belief_outcome_commitment_log",
        "model_knowledge_cutoff_report",
        "phase3_run_snapshot",
        "validated_society_state_panel",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S31ContractError(f"P3.S31.M01 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    phase4 = _parse(
        Phase4SocialHandoffManifest,
        inputs["phase4_social_handoff_manifest"],
        "phase4_social_handoff_manifest",
    )
    variable = _parse(
        VariableEvolutionInputManifest,
        inputs["variable_evolution_input_manifest"],
        "variable_evolution_input_manifest",
    )
    commitments = _parse(
        BeliefOutcomeCommitmentLog,
        inputs["belief_outcome_commitment_log"],
        "belief_outcome_commitment_log",
    )
    cutoff = _parse(
        ModelKnowledgeCutoffReport,
        inputs["model_knowledge_cutoff_report"],
        "model_knowledge_cutoff_report",
    )
    snapshot = _parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"], "phase3_run_snapshot")
    society = _parse(
        ValidatedSocietyStatePanel,
        inputs["validated_society_state_panel"],
        "validated_society_state_panel",
    )

    _validate_common_alignment(context, phase4, commitments, snapshot, society, variable)
    if cutoff.evaluation_end > context.as_of_time:
        raise S31TemporalError("model cutoff evaluation_end exceeds the run as_of_time")
    if cutoff.evaluation_start.date() > context.as_of_time.date():
        raise S31TemporalError("model cutoff evaluation_start is after the run as_of_time")

    items = _artifact_references(context, phase4, variable, commitments, cutoff, snapshot, society)
    schedule = _commitment_schedule(commitments, context)
    reasons: set[str] = set()
    statuses = [item.quality_status for item in items]
    if not schedule:
        reasons.add("NO_BELIEF_COMMITMENTS")
    if cutoff.risk_class == CutoffRiskClass.UNKNOWN:
        reasons.add("MODEL_KNOWLEDGE_CUTOFF_UNKNOWN")
    elif cutoff.risk_class == CutoffRiskClass.CONTAMINATION_RISK:
        reasons.add("MODEL_KNOWLEDGE_CONTAMINATION_RISK")
    if any(item.quality_status == QualityStatus.DEGRADED for item in items):
        reasons.add("UPSTREAM_ARTIFACT_DEGRADED")
    if any(item.quality_status == QualityStatus.BLOCKED for item in items):
        reasons.add("UPSTREAM_ARTIFACT_BLOCKED")
    status = _quality_rollup(statuses)
    if not schedule and status == QualityStatus.PASS:
        status = QualityStatus.DEGRADED

    reproducibility = ReproducibilityKeys(
        snapshot_id=snapshot.snapshot_id,
        configuration_hash=snapshot.configuration_hash,
        model_registry_hash=snapshot.model_registry_hash,
        input_set_hash=_digest([item.model_dump(mode="json") for item in items]),
    )
    core = {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time,
        "pipeline_version": context.pipeline_version,
        "items": [item.model_dump(mode="json") for item in items],
        "commitments": [item.model_dump(mode="json") for item in schedule],
        "cutoff_risk_class": cutoff.risk_class,
        "reproducibility": reproducibility.model_dump(mode="json"),
        "quality_status": status,
        "quality_reasons": sorted(reasons),
    }
    bundle = P9EvaluationEvidenceBundle(
        artifact_id=_artifact_id("p9-evaluation-evidence-bundle", core),
        created_at=context.created_at,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        pipeline_version=context.pipeline_version,
        schema_version="1.0.0",
        items=items,
        commitments=schedule,
        cutoff_risk_class=cutoff.risk_class,
        cutoff_report_ref=next(
            item.artifact_id for item in items if item.artifact_name == "model_knowledge_cutoff_report"
        ),
        reproducibility=reproducibility,
        blind_holdout_policy=BlindHoldoutPolicy(),
        quality_status=status,
        quality_reasons=tuple(sorted(reasons)),
        lineage_id=_lineage_id("p9-evaluation-evidence-bundle", core),
    )
    _scan_forbidden(bundle)
    return _module_result(
        "P3.S31.M01",
        "p9_evaluation_evidence_bundle_builder",
        "p9_evaluation_evidence_bundle",
        bundle,
        started_at,
    )


def _bundle_item_index(bundle: P9EvaluationEvidenceBundle) -> dict[str, ArtifactReference]:
    return {item.artifact_name: item for item in bundle.items}


def build_p9_context_learning_handoff(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
    compatibility_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze the P3→P9 handoff without evaluating, diagnosing, or promoting."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    _scan_forbidden(compatibility_value)
    required = {
        "p9_evaluation_evidence_bundle",
        "phase4_social_handoff_manifest",
        "variable_evolution_input_manifest",
        "phase3_run_snapshot",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S31ContractError(f"P3.S31.M02 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    compatibility = _parse(
        P9ConsumerCompatibilityConfig,
        compatibility_value,
        "p9_consumer_compatibility",
    )
    bundle = _parse(
        P9EvaluationEvidenceBundle,
        inputs["p9_evaluation_evidence_bundle"],
        "p9_evaluation_evidence_bundle",
    )
    phase4 = _parse(
        Phase4SocialHandoffManifest,
        inputs["phase4_social_handoff_manifest"],
        "phase4_social_handoff_manifest",
    )
    variable = _parse(
        VariableEvolutionInputManifest,
        inputs["variable_evolution_input_manifest"],
        "variable_evolution_input_manifest",
    )
    snapshot = _parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"], "phase3_run_snapshot")

    for artifact in (bundle, phase4):
        for field in ("run_id", "cycle_id", "pipeline_version"):
            if getattr(artifact, field) != getattr(context, field):
                raise S31ContractError(
                    f"{artifact.__class__.__name__}.{field} does not match execution context"
                )
        if artifact.as_of_time != context.as_of_time:
            raise S31TemporalError(
                f"{artifact.__class__.__name__}.as_of_time does not match execution context"
            )
    for field in ("run_id", "cycle_id", "pipeline_version"):
        if getattr(snapshot, field) != getattr(context, field):
            raise S31ContractError(f"Phase3RunSnapshot.{field} does not match execution context")
    if snapshot.as_of_time != context.as_of_time:
        raise S31TemporalError("Phase3RunSnapshot.as_of_time does not match execution context")
    if _parse_datetime(variable.as_of_time, "variable_evolution_input_manifest.as_of_time") != context.as_of_time:
        raise S31TemporalError("VariableEvolutionInputManifest.as_of_time does not match execution context")

    actual_hashes = {
        "p9_evaluation_evidence_bundle": _digest(bundle),
        "phase4_social_handoff_manifest": _artifact_content_hash("phase4_social_handoff_manifest", phase4),
        "variable_evolution_input_manifest": _digest(variable),
        "phase3_run_snapshot": _digest(snapshot),
    }
    item_index = _bundle_item_index(bundle)
    expected_pairs = {
        "phase4_social_handoff_manifest": phase4,
        "variable_evolution_input_manifest": variable,
        "phase3_run_snapshot": snapshot,
    }
    for name, artifact in expected_pairs.items():
        expected = item_index[name].content_hash
        actual = (
            _artifact_content_hash(name, artifact)
            if name == "phase4_social_handoff_manifest"
            else _digest(artifact)
        )
        if expected != actual:
            raise S31IntegrityError(f"bundle reference hash mismatch for {name}")

    reasons = set(bundle.quality_reasons)
    if compatibility.consumer_binding_status == ConsumerBindingStatus.CONSUMER_NOT_YET_BOUND:
        reasons.add("P9_CONSUMER_NOT_YET_BOUND")
    elif compatibility.consumer_binding_status == ConsumerBindingStatus.BLOCKED:
        reasons.add("P9_CONSUMER_CONTRACT_BLOCKED")

    if bundle.quality_status == QualityStatus.BLOCKED:
        status = QualityStatus.BLOCKED
    elif compatibility.consumer_binding_status == ConsumerBindingStatus.BLOCKED:
        status = QualityStatus.BLOCKED
    elif (
        bundle.quality_status == QualityStatus.DEGRADED
        or compatibility.consumer_binding_status == ConsumerBindingStatus.CONSUMER_NOT_YET_BOUND
    ):
        status = QualityStatus.DEGRADED
    else:
        status = QualityStatus.PASS

    core = {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time,
        "pipeline_version": context.pipeline_version,
        "artifact_hashes": actual_hashes,
        "consumer_contract_id": compatibility.consumer_contract_id,
        "consumer_contract_hash": compatibility.current_p9_input_contract_hash,
        "consumer_binding_status": compatibility.consumer_binding_status,
        "quality_status": status,
        "quality_reasons": sorted(reasons),
    }
    manifest = P9ContextLearningHandoffManifest(
        manifest_id=_artifact_id("p9-context-learning-handoff", core),
        created_at=context.created_at,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        pipeline_version=context.pipeline_version,
        schema_version="1.0.0",
        artifact_hashes=actual_hashes,
        bundle_artifact_id=bundle.artifact_id,
        bundle_content_hash=actual_hashes["p9_evaluation_evidence_bundle"],
        consumer_contract_id=compatibility.consumer_contract_id,
        consumer_contract_hash=compatibility.current_p9_input_contract_hash,
        consumer_binding_status=compatibility.consumer_binding_status,
        quality_status=status,
        quality_reasons=tuple(sorted(reasons)),
        lineage_id=_lineage_id("p9-context-learning-handoff", core),
    )
    _scan_forbidden(manifest)
    return _module_result(
        "P3.S31.M02",
        "p9_context_learning_handoff_builder",
        "p9_context_learning_handoff_manifest",
        manifest,
        started_at,
    )


__all__ = [
    "S31AuthorityError",
    "S31ContractError",
    "S31Error",
    "S31IntegrityError",
    "S31TemporalError",
    "build_p9_context_learning_handoff",
    "build_p9_evaluation_evidence_bundle",
]
