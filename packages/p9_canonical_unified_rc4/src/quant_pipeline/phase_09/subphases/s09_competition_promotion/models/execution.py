from __future__ import annotations

from pydantic import model_validator

from quant_pipeline.phase_09.contracts.integrity import payload_sha256 as boundary_payload_sha256

from .common import ArtifactReference, CycleRef, NonEmptyStr, Sha256Hex, StrictModel
from .feedback import (
    FeedbackActivationLedgerEntry,
    FeedbackEffectivenessRecord,
    FeedbackPolicyRegistry,
    RootCauseEvidence,
    TargetCapabilitySnapshot,
)
from .frontier import ConfigurationEvaluationCard, ParameterSpaceRegistry
from .leaderboard import LeaderboardPolicy, SubmissionRecord
from .policy import CompetitionObjectiveSpec
from .promotion import PromotionGateReceipt
from .qualification import PairwiseComparisonEvidence




class PromotionSourceContext(StrictModel):
    contract_name: NonEmptyStr = "CONTRACT_P9_S8_TO_S9_PROMOTION_EVIDENCE_V2"
    contract_version: NonEmptyStr = "2.0.0"
    run_id: NonEmptyStr
    cycle: CycleRef
    attribution_bundle_sha256: Sha256Hex
    configuration_ids: tuple[NonEmptyStr, ...]
    context_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_configurations(self) -> "PromotionSourceContext":
        if (
            not self.configuration_ids
            or len(set(self.configuration_ids)) != len(self.configuration_ids)
        ):
            raise ValueError("source configuration IDs must be non-empty and unique")
        expected = boundary_payload_sha256(
            self.model_dump(mode="python", exclude={"context_sha256"})
        )
        if expected != self.context_sha256:
            raise ValueError("S8-S9 source context hash mismatch")
        return self

class PromotionEvidenceInputBundle(StrictModel):
    upstream_bundle_refs: tuple[ArtifactReference, ...]
    source_context: PromotionSourceContext
    objective_spec: CompetitionObjectiveSpec
    configurations: tuple[ConfigurationEvaluationCard, ...]
    parameter_space: ParameterSpaceRegistry
    model_confidence_set_ids: tuple[str, ...]
    submission_ledger: tuple[SubmissionRecord, ...]
    leaderboard_policy: LeaderboardPolicy
    champion_configuration_id: str
    challenger_configuration_ids: tuple[str, ...]
    pairwise_evidence: tuple[PairwiseComparisonEvidence, ...]
    promotion_gate_receipts: tuple[PromotionGateReceipt, ...]
    root_causes: tuple[RootCauseEvidence, ...]
    feedback_policy_registry: FeedbackPolicyRegistry
    previous_feedback_effectiveness: tuple[FeedbackEffectivenessRecord, ...] = ()
    target_capabilities: tuple[TargetCapabilitySnapshot, ...]
    previous_activation_ledger: tuple[FeedbackActivationLedgerEntry, ...] = ()

    @model_validator(mode="after")
    def validate_bundle_identity(self) -> "PromotionEvidenceInputBundle":
        config_ids = {configuration.configuration_id for configuration in self.configurations}
        if self.champion_configuration_id not in config_ids:
            raise ValueError("champion configuration is not present in configuration cards")
        unknown = set(self.challenger_configuration_ids) - config_ids
        if unknown:
            raise ValueError(f"unknown challenger configurations: {sorted(unknown)}")
        if self.champion_configuration_id in self.challenger_configuration_ids:
            raise ValueError("champion cannot also be a challenger")
        if len(set(self.challenger_configuration_ids)) != len(self.challenger_configuration_ids):
            raise ValueError("challenger IDs must be unique")
        if not self.upstream_bundle_refs:
            raise ValueError("at least one upstream bundle reference is required")
        cycle_keys = {(ref.cycle.cycle_id, ref.cycle.ordinal) for ref in self.upstream_bundle_refs}
        if len(cycle_keys) != 1:
            raise ValueError("upstream bundle references must belong to the same source cycle")
        run_ids = {ref.run_id for ref in self.upstream_bundle_refs}
        if len(run_ids) != 1:
            raise ValueError("upstream bundle references must belong to the same run")
        expected_cycle = (self.source_context.cycle.cycle_id, self.source_context.cycle.ordinal)
        if cycle_keys != {expected_cycle} or run_ids != {self.source_context.run_id}:
            raise ValueError("source context does not match upstream evidence references")
        if set(self.source_context.configuration_ids) != config_ids:
            raise ValueError("source context must cover every configuration card exactly")
        matching_attribution = tuple(
            ref for ref in self.upstream_bundle_refs
            if ref.payload_sha256 == self.source_context.attribution_bundle_sha256
            and ref.producer_module_id == "P9.S8.M08"
            and ref.artifact_role == "ATTRIBUTION_RECONCILIATION_BUNDLE_V1"
        )
        if len(matching_attribution) != 1:
            raise ValueError("source attribution must match exactly one P9.S8.M08 artifact")
        for receipt in self.promotion_gate_receipts:
            if (
                receipt.run_id != self.source_context.run_id
                or receipt.cycle != self.source_context.cycle
            ):
                raise ValueError("promotion gate receipt run/cycle mismatch")
            if receipt.source_bundle_sha256 != self.source_context.attribution_bundle_sha256:
                raise ValueError("promotion gate receipt source hash mismatch")
            unknown_subjects = set(receipt.subject_configuration_ids) - set(
                self.challenger_configuration_ids
            )
            if unknown_subjects:
                raise ValueError("promotion gate receipt subject mismatch")
        return self

from datetime import datetime
from pydantic import field_validator

from ..enums import ModuleStatus
from ..hashing import sha256_hex
from .common import ModuleResult, NonEmptyStr, Sha256Hex, UtcTimestampedModel
from .feedback import (
    FeedbackActivationGateOutput,
    FeedbackBuildPolicy,
    FeedbackCandidateManifest,
)
from .frontier import FrontierBuildPolicy, RobustConfigurationFrontier
from .leaderboard import LeaderboardInformationBudgetReport, SubmissionEligibilityReceipt
from .policy import CompetitionObjectivePolicy
from .promotion import PromotionModuleOutput
from .qualification import ChampionChallengerQualificationReport


class S9ExecutionPolicy(StrictModel):
    frontier: FrontierBuildPolicy = FrontierBuildPolicy()
    feedback: FeedbackBuildPolicy = FeedbackBuildPolicy()


class S9ExecutionBundle(UtcTimestampedModel):
    subphase_id: NonEmptyStr = "P9.S9"
    schema_version: NonEmptyStr = "2.0.0"
    source_context: PromotionSourceContext
    objective_result: ModuleResult[CompetitionObjectivePolicy]
    frontier_result: ModuleResult[RobustConfigurationFrontier]
    leaderboard_result: ModuleResult[LeaderboardInformationBudgetReport]
    submission_eligibility: SubmissionEligibilityReceipt
    qualification_result: ModuleResult[ChampionChallengerQualificationReport]
    promotion_result: ModuleResult[PromotionModuleOutput]
    feedback_result: ModuleResult[FeedbackCandidateManifest]
    activation_gate_result: ModuleResult[FeedbackActivationGateOutput]
    created_at: datetime

    @field_validator("subphase_id")
    @classmethod
    def correct_subphase(cls, value: str) -> str:
        if value != "P9.S9":
            raise ValueError("execution bundle subphase_id must be P9.S9")
        return value


class S9ExecutionEnvelope(StrictModel):
    payload: S9ExecutionBundle
    payload_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_payload_hash(self) -> "S9ExecutionEnvelope":
        if self.payload_sha256 != sha256_hex(self.payload):
            raise ValueError("S9 execution envelope hash mismatch")
        return self
