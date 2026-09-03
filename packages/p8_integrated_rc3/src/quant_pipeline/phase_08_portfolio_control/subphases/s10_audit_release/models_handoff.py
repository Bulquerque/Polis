from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import Field, field_validator, model_validator
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError as JsonSchemaValidationError
from .enums import EvidenceClass, OutcomeMaturityHint
from .models_common import ArtifactRef, AuditContext, StrictModel
from .models_qualification import QualificationDecision

class EvaluationCommitment(StrictModel):
    commitment_id: str = Field(min_length=1)
    committed_at: datetime
    outcome_definition: str = Field(min_length=1)
    evaluation_horizons: tuple[str, ...]
    metrics: tuple[str, ...]
    benchmarks: tuple[str, ...]
    policy_hashes: tuple[str, ...]
    holdout_constraints: tuple[str, ...]
    @field_validator("committed_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("committed_at must be timezone-aware")
        return value

class OutcomeEvidenceRecord(StrictModel):
    evidence_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    evidence_class: EvidenceClass
    maturity_hint: OutcomeMaturityHint
    expected_maturity_at: datetime | None = None
    artifact_refs: tuple[ArtifactRef, ...]
    execution_ref: ArtifactRef | None = None
    model_method_id: str | None = None
    @model_validator(mode="after")
    def evidence_semantics(self) -> "OutcomeEvidenceRecord":
        if self.evidence_class == EvidenceClass.FACTUAL_EXECUTED and self.execution_ref is None:
            raise ValueError("FACTUAL_EXECUTED requires execution_ref")
        if self.evidence_class == EvidenceClass.MODEL_BASED_COUNTERFACTUAL and not self.model_method_id:
            raise ValueError("MODEL_BASED_COUNTERFACTUAL requires model_method_id")
        if self.evidence_class != EvidenceClass.MODEL_BASED_COUNTERFACTUAL and self.model_method_id:
            raise ValueError("model_method_id is only valid for model-based counterfactuals")
        return self

class CandidateLineage(StrictModel):
    candidate_id: str = Field(min_length=1)
    p4_view_refs: tuple[ArtifactRef, ...]
    p5_belief_refs: tuple[ArtifactRef, ...]
    p6_candidate_ref: ArtifactRef
    p7_decision_ref: ArtifactRef
    p8_decision_ref: ArtifactRef
    order_refs: tuple[ArtifactRef, ...] = ()
    fill_refs: tuple[ArtifactRef, ...] = ()
    position_refs: tuple[ArtifactRef, ...] = ()


class P9FullEvidenceArtifact(StrictModel):
    role: Literal[
        "nav_panel",
        "exposure_panel",
        "drawdown_panel",
        "optimizer_decision_trace",
        "portfolio_decision_panel",
        "marking_policy_snapshot",
    ]
    payload: dict[str, object] | tuple[dict[str, object], ...]
    schema_name: str = Field(min_length=1)
    schema_version: str = Field(default="1.0.0", min_length=1)
    schema_document: dict[str, object]
    producer_module_id: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    grain: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_artifact(self) -> "P9FullEvidenceArtifact":
        expected_count = len(self.payload) if isinstance(self.payload, tuple) else 1
        if self.record_count != expected_count:
            raise ValueError("record_count must match the structured payload")
        if self.schema_document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError("full-evidence schema must declare Draft 2020-12")
        if self.schema_document.get("title") != self.schema_name:
            raise ValueError("full-evidence schema title must match schema_name")
        expected_type = "array" if isinstance(self.payload, tuple) else "object"
        if self.schema_document.get("type") != expected_type:
            raise ValueError("full-evidence schema type must match payload cardinality")
        try:
            Draft202012Validator.check_schema(self.schema_document)
            Draft202012Validator(self.schema_document).validate(
                list(self.payload) if isinstance(self.payload, tuple) else self.payload
            )
        except (SchemaError, JsonSchemaValidationError) as exc:
            raise ValueError(f"full-evidence payload does not satisfy declared schema: {exc.message}") from exc
        return self


class P9FullEvidenceBundle(StrictModel):
    nav_panel: P9FullEvidenceArtifact
    exposure_panel: P9FullEvidenceArtifact
    drawdown_panel: P9FullEvidenceArtifact
    optimizer_decision_trace: P9FullEvidenceArtifact
    portfolio_decision_panel: P9FullEvidenceArtifact
    marking_policy_snapshot: P9FullEvidenceArtifact

    @model_validator(mode="after")
    def validate_roles(self) -> "P9FullEvidenceBundle":
        for field_name in type(self).model_fields:
            if getattr(self, field_name).role != field_name:
                raise ValueError(f"full-evidence field {field_name} has mismatched role")
        return self


class P9HandoffRequest(StrictModel):
    context: AuditContext
    qualification: QualificationDecision
    evaluation_commitment: EvaluationCommitment
    all_candidate_ids: tuple[str, ...]
    evidence_records: tuple[OutcomeEvidenceRecord, ...]
    lineage_records: tuple[CandidateLineage, ...]
    audit_report_ref: ArtifactRef
    runtime_evidence_ref: ArtifactRef | None = None
    source_artifacts: tuple[ArtifactRef, ...]
    full_evidence: P9FullEvidenceBundle | None = None
    @model_validator(mode="after")
    def commitment_is_predecision(self) -> "P9HandoffRequest":
        if self.evaluation_commitment.committed_at > self.context.decision_time:
            raise ValueError("evaluation commitment must not be created after decision_time")
        if self.qualification.context != self.context:
            raise ValueError("qualification context must equal handoff context")
        return self

class P9EvaluationHandoff(StrictModel):
    handoff_id: str = Field(min_length=1)
    context: AuditContext
    qualification: QualificationDecision
    evaluation_commitment: EvaluationCommitment
    all_candidate_ids: tuple[str, ...]
    evidence_records: tuple[OutcomeEvidenceRecord, ...]
    lineage_records: tuple[CandidateLineage, ...]
    audit_report_ref: ArtifactRef
    runtime_evidence_ref: ArtifactRef | None
    source_artifacts: tuple[ArtifactRef, ...]
    full_evidence: P9FullEvidenceBundle | None = None
    production_promotion_allowed: Literal[False] = False
