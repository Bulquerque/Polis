from __future__ import annotations

from dataclasses import dataclass

from quant_pipeline.phase_09.contracts.artifacts import ArtifactReference
from quant_pipeline.phase_09.contracts.base import Availability
from quant_pipeline.phase_09.contracts.handoff import P8EvaluationHandoffV1, P8HandoffMode
from quant_pipeline.phase_09.contracts.integrity import (
    IntegrityEnvelope,
    payload_sha256,
    sha256_bytes,
    verify_integrity,
)
from quant_pipeline.phase_09.contracts.receipts import ConsumerReceipt, ConsumerReceiptPayload
from quant_pipeline.phase_09.contracts.registry import (
    ArtifactSchemaRegistrySnapshot,
    ContractCompatibilityMatrix,
    ModuleRegistrySnapshot,
)
from quant_pipeline.phase_09.contracts.validation import (
    HandoffValidationReport,
    HandoffValidationStatus,
    ValidatedP8EvaluationHandoff,
    ValidationCheck,
)

from .ports import ArtifactStoreError, ArtifactStoreReadPort

FULL_REQUIRED_ROLES = frozenset(
    {
        "candidate_terminal_state_ledger",
        "portfolio_decision_panel",
        "optimizer_decision_trace",
        "orders_panel",
        "fills_panel",
        "ordered_event_ledger",
        "physical_position_ledger",
        "virtual_candidate_ledger",
        "cash_ledger",
        "premium_ledger",
        "cost_ledger",
        "margin_ledger",
        "collateral_ledger",
        "lifecycle_event_ledger",
        "valuation_panel",
        "nav_panel",
        "pnl_panel",
        "exposure_panel",
        "drawdown_panel",
        "replay_checkpoint_manifest",
        "replay_expected_state",
        "marking_policy_snapshot",
        "lineage_manifest",
        "maturity_subject_manifest",
        "executed_outcome_panel",
        "market_mark_panel",
    }
)

P8_NATIVE_REQUIRED_ROLES = frozenset(
    {
        "candidate_terminal_state_ledger",
        "orders_panel",
        "fills_panel",
        "ordered_event_ledger",
        "physical_position_ledger",
        "virtual_candidate_ledger",
        "cash_ledger",
        "premium_ledger",
        "cost_ledger",
        "margin_ledger",
        "collateral_ledger",
        "lifecycle_event_ledger",
        "valuation_panel",
        "pnl_panel",
        "replay_checkpoint_manifest",
        "replay_expected_state",
        "lineage_manifest",
        "maturity_subject_manifest",
        "executed_outcome_panel",
        "market_mark_panel",
    }
)


LEGACY_REQUIRED_ROLES = frozenset(
    {
        "portfolio_backtest_result",
        "performance_report",
        "backtest_audit_report",
        "portfolio_diagnostics_report",
        "orders_panel",
        "fills_panel",
        "position_ledger",
        "cash_ledger",
        "premium_ledger",
        "cost_ledger",
        "margin_ledger",
        "pnl_panel",
        "equity_curve_panel",
        "exposure_panel",
        "drawdown_panel",
        "ranking_context_snapshot",
        "score_decomposition_snapshot",
        "ranking_audit_snapshot",
    }
)


@dataclass(frozen=True, slots=True)
class HandoffValidationOutcome:
    validated: ValidatedP8EvaluationHandoff | None
    report: HandoffValidationReport


class P8EvaluationHandoffValidator:
    module_id = "P9.S1.M01"

    def __init__(
        self,
        *,
        compatibility: ContractCompatibilityMatrix,
        module_registry: ModuleRegistrySnapshot,
        schema_registry: ArtifactSchemaRegistrySnapshot,
        artifact_store: ArtifactStoreReadPort,
    ) -> None:
        self._compatibility = compatibility
        self._module_registry = module_registry
        self._schema_registry = schema_registry
        self._artifact_store = artifact_store

    def validate(self, handoff: P8EvaluationHandoffV1, *, evaluation_as_of=None) -> HandoffValidationOutcome:
        checks: list[ValidationCheck] = []
        accepted: list[ArtifactReference] = []
        rejected_ids: list[str] = []
        reserved_ids: list[str] = []
        limitations: list[str] = list(handoff.payload.limitations)

        contract_ok = self._compatibility.supports(
            handoff.payload.contract_name,
            handoff.payload.contract_version,
            handoff.payload.mode.value,
        )
        checks.append(
            self._check(
                "contract_compatibility",
                contract_ok,
                "P9_S1_HANDOFF_SCHEMA_INCOMPATIBLE",
                "contract/mode is not present in the frozen compatibility matrix",
            )
        )

        integrity_ok = verify_integrity(handoff.payload, handoff.integrity)
        checks.append(
            self._check(
                "handoff_integrity",
                integrity_ok,
                "P9_S1_HANDOFF_HASH_MISMATCH",
                "handoff payload hash does not match the integrity envelope",
            )
        )

        temporal_publication_ok = evaluation_as_of is None or handoff.payload.published_at <= evaluation_as_of
        checks.append(
            self._check(
                "handoff_publication_time",
                temporal_publication_ok,
                "P9_S1_HANDOFF_CLOCK_INCONSISTENT",
                "P8 handoff was published after P9 evaluation_as_of",
            )
        )

        slots_by_role = {slot.role: slot for slot in handoff.payload.artifacts}
        if handoff.payload.mode is P8HandoffMode.FULL_V1:
            required_roles = FULL_REQUIRED_ROLES
        elif handoff.payload.mode is P8HandoffMode.P8_NATIVE_0_3_LIMITED:
            required_roles = P8_NATIVE_REQUIRED_ROLES
        else:
            required_roles = LEGACY_REQUIRED_ROLES
        missing_roles = sorted(required_roles - set(slots_by_role))
        present_required = all(
            slots_by_role[role].reference is not None
            for role in required_roles
            if role in slots_by_role
        )
        required_ok = not missing_roles and present_required
        details = tuple([f"missing role: {role}" for role in missing_roles])
        checks.append(
            self._check(
                "required_artifacts",
                required_ok,
                "P9_S1_HANDOFF_REQUIRED_ARTIFACT_MISSING",
                *(details or ("one or more required artifact roles are explicitly absent",)),
            )
        )

        run_cycle_ok = True
        clock_ok = True
        registry_ok = True
        content_ok = True
        schema_ok = True
        for slot in handoff.payload.artifacts:
            if slot.reference is None:
                reserved_ids.append(f"absence:{slot.role}")
                continue
            reference = slot.reference
            if (
                reference.run_id != handoff.payload.run_id
                or reference.cycle_id != handoff.payload.cycle_id
                or reference.backtest_id != handoff.payload.backtest_id
            ):
                run_cycle_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if reference.computed_at > handoff.payload.published_at:
                clock_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if not self._module_registry.contains(reference.producer_module_id):
                registry_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            binding = self._schema_registry.binding(
                reference.schema_name,
                reference.artifact_schema_version,
            )
            if binding is None:
                schema_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if binding.schema_sha256 != reference.schema_sha256:
                schema_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if reference.producer_module_id not in binding.allowed_producer_module_ids:
                registry_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if reference.availability is Availability.UNAVAILABLE:
                reserved_ids.append(reference.artifact_id)
                continue
            try:
                payload = self._artifact_store.read_bytes(reference.location)
            except ArtifactStoreError:
                content_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            if sha256_bytes(payload) != reference.content_sha256:
                content_ok = False
                rejected_ids.append(reference.artifact_id)
                continue
            accepted.append(reference)

        checks.extend(
            (
                self._check(
                    "run_cycle_consistency",
                    run_cycle_ok,
                    "P9_S1_HANDOFF_CLOCK_INCONSISTENT",
                    "artifact run/cycle/backtest IDs do not match the handoff",
                ),
                self._check(
                    "clock_consistency",
                    clock_ok,
                    "P9_S1_HANDOFF_CLOCK_INCONSISTENT",
                    "artifact computed_at is later than handoff published_at",
                ),
                self._check(
                    "module_registry_bindings",
                    registry_ok,
                    "P9_S1_HANDOFF_SCHEMA_INCOMPATIBLE",
                    "producer module is unknown or not authorized for its schema",
                ),
                self._check(
                    "schema_registry_bindings",
                    schema_ok,
                    "P9_S1_HANDOFF_SCHEMA_INCOMPATIBLE",
                    "artifact schema binding is absent or hash-mismatched",
                ),
                self._check(
                    "artifact_content_hashes",
                    content_ok,
                    "P9_S1_HANDOFF_HASH_MISMATCH",
                    "artifact bytes are unavailable or hash-mismatched",
                ),
            )
        )

        if handoff.payload.mode is P8HandoffMode.P8_NATIVE_0_3_LIMITED:
            limitations.extend(
                (
                    "P8 0.3 native handoff lacks one or more FULL evaluation artifacts",
                    "native limited evidence cannot authorize promotion",
                )
            )
            checks.append(
                ValidationCheck(
                    check_id="p8_native_limited_mode",
                    passed=True,
                    details=("P8 0.3 native handoff accepted only in LIMITED mode",),
                )
            )
        elif handoff.payload.mode is P8HandoffMode.LEGACY_RC4_1_LIMITED:
            limitations.extend(
                (
                    "legacy P8 lineage is not transitively proven",
                    "legacy P8 lacks complete event/checkpoint semantics",
                    "legacy P8 cannot support full causal attribution or promotion",
                )
            )
            checks.append(
                ValidationCheck(
                    check_id="legacy_mode_limitation",
                    passed=True,
                    details=("legacy handoff accepted only in LIMITED mode",),
                )
            )

        blocking = any(not check.passed for check in checks)
        if blocking:
            if not contract_ok:
                status = HandoffValidationStatus.REJECTED_CONTRACT
            elif not integrity_ok or not content_ok:
                status = HandoffValidationStatus.REJECTED_INTEGRITY
            else:
                status = HandoffValidationStatus.REJECTED_INCOMPLETE
        elif handoff.payload.mode in {
            P8HandoffMode.P8_NATIVE_0_3_LIMITED,
            P8HandoffMode.LEGACY_RC4_1_LIMITED,
        }:
            status = HandoffValidationStatus.ACCEPTED_LIMITED
        else:
            status = HandoffValidationStatus.ACCEPTED_FULL

        report = HandoffValidationReport(
            status=status,
            checks=tuple(checks),
            limitations=tuple(dict.fromkeys(limitations)),
        )
        if blocking:
            return HandoffValidationOutcome(validated=None, report=report)

        accepted_ids = tuple(sorted(reference.artifact_id for reference in accepted))
        rejected_tuple = tuple(sorted(set(rejected_ids)))
        reserved_tuple = tuple(sorted(set(reserved_ids)))
        reason_codes = tuple(
            sorted(
                {
                    code
                    for check in checks
                    if not check.passed
                    for code in check.reason_codes
                }
                | (
                    {
                        "P9_S1_HANDOFF_P8_NATIVE_LIMITED"
                        if handoff.payload.mode is P8HandoffMode.P8_NATIVE_0_3_LIMITED
                        else "P9_S1_HANDOFF_LEGACY_LIMITED"
                    }
                    if status is HandoffValidationStatus.ACCEPTED_LIMITED
                    else set()
                )
            )
        )
        receipt_payload = ConsumerReceiptPayload(
            consumer_module_id=self.module_id,
            source_contract_name=handoff.payload.contract_name,
            source_contract_version=handoff.payload.contract_version,
            source_payload_sha256=handoff.integrity.payload_sha256,
            accepted_artifact_ids=accepted_ids,
            rejected_artifact_ids=rejected_tuple,
            reserved_artifact_ids=reserved_tuple,
            reason_codes=reason_codes,
        )
        receipt = ConsumerReceipt(
            payload=receipt_payload,
            integrity=IntegrityEnvelope(payload_sha256=payload_sha256(receipt_payload)),
        )
        validated = ValidatedP8EvaluationHandoff(
            handoff=handoff.payload,
            accepted_artifacts=tuple(sorted(accepted, key=lambda item: item.artifact_id)),
            status=status,
            limitations=report.limitations,
            consumer_receipt=receipt,
            validation_report=report,
        )
        return HandoffValidationOutcome(validated=validated, report=report)

    @staticmethod
    def _check(
        check_id: str,
        passed: bool,
        reason_code: str,
        *details: str,
    ) -> ValidationCheck:
        if passed:
            return ValidationCheck(check_id=check_id, passed=True, details=tuple(details))
        return ValidationCheck(
            check_id=check_id,
            passed=False,
            reason_codes=(reason_code,),
            details=tuple(details),
        )
