from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.contracts.cohort import (
    CohortPolicyRegistry,
    HoldoutAccessLedger,
    ResearchCommitmentRegistry,
)
from quant_pipeline.phase_09.contracts.handoff import P8EvaluationHandoffV1
from quant_pipeline.phase_09.contracts.integrity import (
    IntegrityEnvelope,
    payload_sha256,
    sha256_bytes,
)
from quant_pipeline.phase_09.contracts.lineage import LineageResolutionStatus
from quant_pipeline.phase_09.contracts.maturity import (
    MaturitySubjectManifest,
    OutcomeMaturityPolicyRegistry,
)
from quant_pipeline.phase_09.contracts.outcomes import (
    ExecutedOutcomePanel,
    MarketMarkPanel,
    MarkingPolicy,
)
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    SubphaseExecutionReceipt,
    SubphaseExecutionReceiptPayload,
)
from quant_pipeline.phase_09.contracts.registry import (
    ArtifactSchemaRegistrySnapshot,
    ContractCompatibilityMatrix,
    ModuleRegistrySnapshot,
)
from quant_pipeline.phase_09.contracts.replay import (
    OrderedEventLedger,
    ReplayCheckpoint,
    ReplayPolicy,
    ReplayState,
)
from quant_pipeline.phase_09.contracts.s1 import S1ExecutionOutputs
from quant_pipeline.phase_09.contracts.validation import HandoffValidationStatus

from .clock import ClockPort
from .common import build_integrity, build_module_receipt
from .m01_handoff_validator import P8EvaluationHandoffValidator
from .m02_lineage_resolver import ImmutableLineageChainResolver, LineageResolutionPolicy
from .m03_replay_auditor import DeterministicReplayIntegrityAuditor
from .m04_maturity_classifier import OutcomeMaturityAndCensoringClassifier
from .m05_outcome_assembler import RealizedOutcomeAndMarkQualityAssembler
from .m06_cohort_commitment_matcher import EvaluationCohortAndCommitmentMatcher
from .ports import ArtifactStoreReadPort

TModel = TypeVar("TModel", bound=BaseModel)
EXPECTED_MODULE_IDS = tuple(f"P9.S1.M0{index}" for index in range(1, 7))


class S1Runner:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStoreReadPort,
        compatibility: ContractCompatibilityMatrix,
        module_registry: ModuleRegistrySnapshot,
        schema_registry: ArtifactSchemaRegistrySnapshot,
        clock: ClockPort,
    ) -> None:
        self._artifact_store = artifact_store
        self._compatibility = compatibility
        self._module_registry = module_registry
        self._schema_registry = schema_registry
        self._clock = clock

    def run(
        self,
        *,
        handoff: P8EvaluationHandoffV1,
        lineage_policy: LineageResolutionPolicy,
        replay_policy: ReplayPolicy,
        maturity_policies: OutcomeMaturityPolicyRegistry,
        commitments: ResearchCommitmentRegistry,
        cohort_policies: CohortPolicyRegistry,
        holdout_access: HoldoutAccessLedger,
        evaluation_as_of,
        metric_family: str = "primary",
    ) -> S1ExecutionOutputs:
        receipts: list[ModuleExecutionReceipt] = []
        limitations: list[str] = []

        m01_start = self._clock.now()
        handoff_outcome = P8EvaluationHandoffValidator(
            compatibility=self._compatibility,
            module_registry=self._module_registry,
            schema_registry=self._schema_registry,
            artifact_store=self._artifact_store,
        ).validate(handoff, evaluation_as_of=evaluation_as_of)
        m01_status = self._handoff_module_status(handoff_outcome.report.status)
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M01",
                status=m01_status,
                started_at=m01_start,
                completed_at=self._clock.now(),
                input_artifact_ids=tuple(
                    slot.reference.artifact_id
                    for slot in handoff.payload.artifacts
                    if slot.reference is not None
                ),
                reason_codes=self._report_reason_codes(handoff_outcome.report),
                limitations=handoff_outcome.report.limitations,
                implementation_sha256=self._implementation_sha256("m01_handoff_validator.py"),
                policy_sha256=payload_sha256(self._compatibility),
            )
        )
        limitations.extend(handoff_outcome.report.limitations)
        if handoff_outcome.validated is None:
            receipts.extend(self._skipped_receipts("P9_S1_HANDOFF_REJECTED", start_index=2))
            subphase = self._subphase_receipt(receipts, ModuleStatus.INVALID, limitations)
            return S1ExecutionOutputs(
                handoff_report=handoff_outcome.report,
                module_receipts=tuple(receipts),
                subphase_receipt=subphase,
                limitations=tuple(dict.fromkeys(limitations)),
            )

        validated = handoff_outcome.validated
        m02_start = self._clock.now()
        lineage_outcome = ImmutableLineageChainResolver(self._artifact_store).resolve(
            validated,
            lineage_policy,
        )
        m02_status = self._lineage_module_status(lineage_outcome.gap_report.status)
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M02",
                status=m02_status,
                started_at=m02_start,
                completed_at=self._clock.now(),
                input_artifact_ids=tuple(
                    ref.artifact_id
                    for ref in validated.accepted_artifacts
                    if ref.schema_name == "lineage_manifest"
                    or ref.artifact_type == "lineage_manifest"
                ),
                reason_codes=tuple(
                    sorted({gap.reason_code for gap in lineage_outcome.gap_report.gaps})
                ),
                limitations=tuple(gap.description for gap in lineage_outcome.gap_report.gaps),
                implementation_sha256=self._implementation_sha256("m02_lineage_resolver.py"),
                policy_sha256=payload_sha256(
                    {
                        "required_phase_ids": lineage_policy.required_phase_ids,
                        "verify_all_artifact_hashes": lineage_policy.verify_all_artifact_hashes,
                        "allow_nonmaterial_gaps": lineage_policy.allow_nonmaterial_gaps,
                    }
                ),
            )
        )
        if lineage_outcome.graph is None or lineage_outcome.graph.status in {
            LineageResolutionStatus.CORRUPT,
            LineageResolutionStatus.UNAVAILABLE,
        }:
            receipts.extend(self._skipped_receipts("P9_S1_LINEAGE_BLOCKED", start_index=3))
            subphase = self._subphase_receipt(receipts, ModuleStatus.INVALID, limitations)
            return S1ExecutionOutputs(
                validated_handoff=validated,
                handoff_report=handoff_outcome.report,
                lineage_gap_report=lineage_outcome.gap_report,
                lineage_receipt=lineage_outcome.receipt,
                module_receipts=tuple(receipts),
                subphase_receipt=subphase,
                limitations=tuple(dict.fromkeys(limitations)),
            )

        graph = lineage_outcome.graph
        try:
            checkpoint = self._parse_role(validated, "replay_checkpoint_manifest", ReplayCheckpoint)
            ledger = self._parse_role(validated, "ordered_event_ledger", OrderedEventLedger)
            expected_state = self._parse_role(validated, "replay_expected_state", ReplayState)
        except ValueError as exc:
            receipts.extend(self._blocked_from(3, "P9_S1_REPLAY_INPUT_MISSING", str(exc)))
            subphase = self._subphase_receipt(receipts, ModuleStatus.LIMITED, limitations)
            return S1ExecutionOutputs(
                validated_handoff=validated,
                handoff_report=handoff_outcome.report,
                lineage_graph=graph,
                lineage_gap_report=lineage_outcome.gap_report,
                lineage_receipt=lineage_outcome.receipt,
                module_receipts=tuple(receipts),
                subphase_receipt=subphase,
                limitations=tuple(dict.fromkeys(limitations + [str(exc)])),
            )

        m03_start = self._clock.now()
        replay_outcome = DeterministicReplayIntegrityAuditor().audit(
            checkpoint=checkpoint,
            event_ledger=ledger,
            expected_state=expected_state,
            policy=replay_policy,
        )
        m03_status = self._replay_module_status(replay_outcome.report.status.value)
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M03",
                status=m03_status,
                started_at=m03_start,
                completed_at=self._clock.now(),
                input_artifact_ids=(
                    checkpoint.payload.checkpoint_id,
                    ledger.payload.ledger_id,
                ),
                reason_codes=replay_outcome.report.reason_codes,
                limitations=tuple(item.message for item in replay_outcome.exceptions.exceptions),
                implementation_sha256=self._implementation_sha256("m03_replay_auditor.py"),
                policy_sha256=payload_sha256(replay_policy),
            )
        )
        if m03_status in {ModuleStatus.INVALID, ModuleStatus.FAILED}:
            receipts.extend(self._skipped_receipts("P9_S1_REPLAY_BLOCKED", start_index=4))
            subphase = self._subphase_receipt(receipts, ModuleStatus.INVALID, limitations)
            return S1ExecutionOutputs(
                validated_handoff=validated,
                handoff_report=handoff_outcome.report,
                lineage_graph=graph,
                lineage_gap_report=lineage_outcome.gap_report,
                lineage_receipt=lineage_outcome.receipt,
                replay_report=replay_outcome.report,
                replay_hashes=replay_outcome.hashes,
                replay_exceptions=replay_outcome.exceptions,
                module_receipts=tuple(receipts),
                subphase_receipt=subphase,
                limitations=tuple(dict.fromkeys(limitations)),
            )

        subjects = self._parse_role(validated, "maturity_subject_manifest", MaturitySubjectManifest)
        m04_start = self._clock.now()
        maturity_panel, eligibility_panel, maturity_trace = (
            OutcomeMaturityAndCensoringClassifier().classify(
                manifest=subjects,
                policy_registry=maturity_policies,
                evaluation_as_of=evaluation_as_of,
            )
        )
        maturity_blockers = tuple(
            sorted(
                {
                    reason_code
                    for decision in maturity_panel.decisions
                    if not decision.eligible
                    for reason_code in decision.reason_codes
                }
            )
        )
        m04_status = (
            ModuleStatus.SUCCESS
            if eligibility_panel.eligible_keys
            else ModuleStatus.LIMITED
        )
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M04",
                status=m04_status,
                started_at=m04_start,
                completed_at=self._clock.now(),
                reason_codes=() if m04_status is ModuleStatus.SUCCESS else maturity_blockers,
                implementation_sha256=self._implementation_sha256("m04_maturity_classifier.py"),
                policy_sha256=payload_sha256(maturity_policies),
            )
        )

        executed = self._parse_role(validated, "executed_outcome_panel", ExecutedOutcomePanel)
        marks = self._parse_role(validated, "market_mark_panel", MarketMarkPanel)
        marking_policy = self._parse_role(validated, "marking_policy_snapshot", MarkingPolicy)
        m05_start = self._clock.now()
        outcome_panel, counterfactuals, mark_report, assembly_receipt = (
            RealizedOutcomeAndMarkQualityAssembler().assemble(
                subjects=subjects,
                maturity_panel=maturity_panel,
                executed_outcomes=executed.records,
                market_marks=marks.records,
                policy=marking_policy,
                evaluation_as_of=evaluation_as_of,
                metric_family=metric_family,
            )
        )
        m05_status = (
            ModuleStatus.SUCCESS
            if mark_report.unavailable_count == 0
            else ModuleStatus.LIMITED
        )
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M05",
                status=m05_status,
                started_at=m05_start,
                completed_at=self._clock.now(),
                reason_codes=(
                    ("P9_S1_MARK_COVERAGE_LIMITED",)
                    if m05_status is ModuleStatus.LIMITED
                    else ()
                ),
                limitations=(
                    f"{mark_report.unavailable_count} subjects lack an observable outcome",
                )
                if mark_report.unavailable_count
                else (),
                implementation_sha256=self._implementation_sha256("m05_outcome_assembler.py"),
                policy_sha256=payload_sha256(marking_policy),
            )
        )

        m06_start = self._clock.now()
        cohort_outcome = EvaluationCohortAndCommitmentMatcher().match(
            subjects=subjects,
            maturity_panel=maturity_panel,
            outcomes=outcome_panel,
            lineage=graph,
            commitments=commitments,
            cohort_policies=cohort_policies,
            holdout_access=holdout_access,
            evaluation_as_of=evaluation_as_of,
            metric_family=metric_family,
        )
        m06_status = self._cohort_module_status(cohort_outcome.report.state.value)
        receipts.append(
            build_module_receipt(
                module_id="P9.S1.M06",
                status=m06_status,
                started_at=m06_start,
                completed_at=self._clock.now(),
                reason_codes=cohort_outcome.report.reason_codes,
                limitations=cohort_outcome.report.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m06_cohort_commitment_matcher.py"
                ),
                policy_sha256=payload_sha256(cohort_policies),
            )
        )
        final_status = self._aggregate_status(receipts)
        subphase = self._subphase_receipt(receipts, final_status, limitations)
        return S1ExecutionOutputs(
            validated_handoff=validated,
            handoff_report=handoff_outcome.report,
            lineage_graph=graph,
            lineage_gap_report=lineage_outcome.gap_report,
            lineage_receipt=lineage_outcome.receipt,
            replay_report=replay_outcome.report,
            replay_hashes=replay_outcome.hashes,
            replay_exceptions=replay_outcome.exceptions,
            maturity_panel=maturity_panel,
            eligibility_panel=eligibility_panel,
            maturity_trace=maturity_trace,
            realized_outcomes=outcome_panel,
            counterfactual_marks=counterfactuals,
            mark_quality_report=mark_report,
            outcome_assembly_receipt=assembly_receipt,
            frozen_cohort=cohort_outcome.cohort,
            commitment_report=cohort_outcome.report,
            holdout_report=cohort_outcome.holdout_report,
            module_receipts=tuple(receipts),
            subphase_receipt=subphase,
            limitations=tuple(dict.fromkeys(limitations)),
        )

    def _parse_role(self, validated, role: str, model_type: type[TModel]) -> TModel:
        slot = validated.handoff.slot(role)
        if slot is None or slot.reference is None:
            raise ValueError(f"required role unavailable: {role}")
        raw = self._artifact_store.read_bytes(slot.reference.location)
        if sha256_bytes(raw) != slot.reference.content_sha256:
            raise ValueError(f"artifact hash mismatch while parsing role: {role}")
        return model_type.model_validate_json(raw)

    def _skipped_receipts(self, reason_code: str, start_index: int) -> list[ModuleExecutionReceipt]:
        return [
            build_module_receipt(
                module_id=f"P9.S1.M0{index}",
                status=ModuleStatus.SKIPPED_UPSTREAM_BLOCKED,
                started_at=self._clock.now(),
                completed_at=self._clock.now(),
                reason_codes=(reason_code,),
                limitations=("upstream gate prevented safe execution",),
                implementation_sha256=self._implementation_sha256(
                    {
                        2: "m02_lineage_resolver.py",
                        3: "m03_replay_auditor.py",
                        4: "m04_maturity_classifier.py",
                        5: "m05_outcome_assembler.py",
                        6: "m06_cohort_commitment_matcher.py",
                    }[index]
                ),
                policy_sha256="0" * 64,
            )
            for index in range(start_index, 7)
        ]

    def _blocked_from(self, start_index: int, reason_code: str, limitation: str):
        return [
            build_module_receipt(
                module_id=f"P9.S1.M0{index}",
                status=(
                    ModuleStatus.UNAVAILABLE
                    if index == start_index
                    else ModuleStatus.SKIPPED_UPSTREAM_BLOCKED
                ),
                started_at=self._clock.now(),
                completed_at=self._clock.now(),
                reason_codes=(reason_code,),
                limitations=(limitation,),
                implementation_sha256=self._implementation_sha256(
                    {
                        3: "m03_replay_auditor.py",
                        4: "m04_maturity_classifier.py",
                        5: "m05_outcome_assembler.py",
                        6: "m06_cohort_commitment_matcher.py",
                    }[index]
                ),
                policy_sha256="0" * 64,
            )
            for index in range(start_index, 7)
        ]

    def _subphase_receipt(
        self,
        receipts: list[ModuleExecutionReceipt],
        status: ModuleStatus,
        limitations: list[str],
    ) -> SubphaseExecutionReceipt:
        payload = SubphaseExecutionReceiptPayload(
            subphase_id="P9.S1",
            expected_module_ids=EXPECTED_MODULE_IDS,
            module_receipts=tuple(receipts),
            status=status,
            limitations=tuple(dict.fromkeys(limitations)),
        )
        return SubphaseExecutionReceipt(payload=payload, integrity=build_integrity(payload))

    @staticmethod
    def _aggregate_status(receipts: list[ModuleExecutionReceipt]) -> ModuleStatus:
        statuses = {receipt.payload.status for receipt in receipts}
        if ModuleStatus.FAILED in statuses:
            return ModuleStatus.FAILED
        if ModuleStatus.INVALID in statuses:
            return ModuleStatus.INVALID
        if statuses == {ModuleStatus.SUCCESS}:
            return ModuleStatus.SUCCESS
        return ModuleStatus.LIMITED

    @staticmethod
    def _handoff_module_status(status: HandoffValidationStatus) -> ModuleStatus:
        return {
            HandoffValidationStatus.ACCEPTED_FULL: ModuleStatus.SUCCESS,
            HandoffValidationStatus.ACCEPTED_LIMITED: ModuleStatus.LIMITED,
            HandoffValidationStatus.REJECTED_CONTRACT: ModuleStatus.INVALID,
            HandoffValidationStatus.REJECTED_INTEGRITY: ModuleStatus.INVALID,
            HandoffValidationStatus.REJECTED_INCOMPLETE: ModuleStatus.INVALID,
        }[status]

    @staticmethod
    def _lineage_module_status(status: LineageResolutionStatus) -> ModuleStatus:
        return {
            LineageResolutionStatus.RESOLVED_COMPLETE: ModuleStatus.SUCCESS,
            LineageResolutionStatus.RESOLVED_WITH_NONMATERIAL_GAPS: ModuleStatus.LIMITED,
            LineageResolutionStatus.INCOMPLETE_MATERIAL: ModuleStatus.LIMITED,
            LineageResolutionStatus.CORRUPT: ModuleStatus.INVALID,
            LineageResolutionStatus.UNAVAILABLE: ModuleStatus.UNAVAILABLE,
        }[status]

    @staticmethod
    def _replay_module_status(status: str) -> ModuleStatus:
        if status == "REPLAY_EXACT":
            return ModuleStatus.SUCCESS
        if status == "REPLAY_NUMERICALLY_EQUIVALENT":
            return ModuleStatus.LIMITED
        return ModuleStatus.INVALID

    @staticmethod
    def _cohort_module_status(state: str) -> ModuleStatus:
        if state == "COHORT_FROZEN":
            return ModuleStatus.SUCCESS
        if state == "COHORT_LIMITED":
            return ModuleStatus.LIMITED
        if state == "INSUFFICIENT_ELIGIBLE_SAMPLE":
            return ModuleStatus.INSUFFICIENT_EVIDENCE
        return ModuleStatus.INVALID

    @staticmethod
    def _report_reason_codes(report) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    reason_code
                    for check in report.checks
                    if not check.passed
                    for reason_code in check.reason_codes
                }
                | (
                    {"P9_S1_HANDOFF_LEGACY_LIMITED"}
                    if report.status is HandoffValidationStatus.ACCEPTED_LIMITED
                    else set()
                )
            )
        )

    @staticmethod
    def _implementation_sha256(filename: str) -> str:
        path = Path(__file__).with_name(filename)
        return hashlib.sha256(path.read_bytes()).hexdigest()
