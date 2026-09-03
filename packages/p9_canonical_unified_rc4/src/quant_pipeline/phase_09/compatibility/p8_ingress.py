from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from quant_pipeline.phase_09.contracts.artifacts import ArtifactReference, ArtifactSlot
from quant_pipeline.phase_09.contracts.base import Availability, ModuleStatus
from quant_pipeline.phase_09.contracts.handoff import (
    CandidateTerminalCounts,
    P8EvaluationHandoffPayload,
    P8EvaluationHandoffV1,
    P8HandoffMode,
)
from quant_pipeline.phase_09.contracts.integrity import (
    IntegrityEnvelope,
    canonical_json_bytes,
    payload_sha256,
    sha256_bytes,
)
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    ModuleExecutionReceiptPayload,
)
from quant_pipeline.phase_09.contracts.registry import (
    ArtifactSchemaBinding,
    ArtifactSchemaRegistrySnapshot,
    ContractCompatibilityEntry,
    ContractCompatibilityMatrix,
    ModuleBinding,
    ModuleRegistrySnapshot,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import (
    ArtifactStoreWritePort,
)

from .errors import ContractMismatchError, EvidenceIncompleteError
from .models import P8NativePublicationRequest, SupplementalArtifact
from .runtime import model_data
from .registry import load_cross_phase_compatibility_matrix

_NATIVE_REQUIRED = frozenset({
    "candidate_terminal_state_ledger", "orders_panel", "fills_panel",
    "ordered_event_ledger", "physical_position_ledger", "virtual_candidate_ledger",
    "cash_ledger", "premium_ledger", "cost_ledger", "margin_ledger",
    "collateral_ledger", "lifecycle_event_ledger", "valuation_panel", "pnl_panel",
    "replay_checkpoint_manifest", "replay_expected_state", "lineage_manifest",
    "maturity_subject_manifest", "executed_outcome_panel", "market_mark_panel",
})
_FULL_REQUIRED = frozenset({
    "candidate_terminal_state_ledger", "portfolio_decision_panel", "optimizer_decision_trace",
    "orders_panel", "fills_panel", "ordered_event_ledger", "physical_position_ledger",
    "virtual_candidate_ledger", "cash_ledger", "premium_ledger", "cost_ledger",
    "margin_ledger", "collateral_ledger", "lifecycle_event_ledger", "valuation_panel",
    "nav_panel", "pnl_panel", "exposure_panel", "drawdown_panel",
    "replay_checkpoint_manifest", "replay_expected_state", "marking_policy_snapshot",
    "lineage_manifest", "maturity_subject_manifest", "executed_outcome_panel",
    "market_mark_panel",
})


@dataclass(frozen=True, slots=True)
class P8NativePublication:
    handoff: P8EvaluationHandoffV1
    module_registry: ModuleRegistrySnapshot
    schema_registry: ArtifactSchemaRegistrySnapshot
    compatibility_matrix: ContractCompatibilityMatrix
    mode: P8HandoffMode
    missing_full_roles: tuple[str, ...]


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python", exclude_none=False)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractMismatchError("P8 datetime must be timezone-aware")
    return value.astimezone(UTC)


def _category(entries: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [row for row in entries if str(row.get("category")) == name]


def _candidate_counts(states: list[dict[str, Any]]) -> CandidateTerminalCounts:
    selected_states = {"ADMITTED", "EXECUTED", "PARTIALLY_EXECUTED"}
    no_action_states = {"ABSTAINED", "NO_ACTION_VALID"}
    execution_failed_states = {"NOT_EXECUTABLE"}
    rejected_states = {"BLOCKED", "REDUNDANT", "NOT_SIZABLE", "RISK_BLOCKED"}
    values = [str(row["terminal_state"]) for row in states]
    return CandidateTerminalCounts(
        received=len(values),
        selected=sum(value in selected_states for value in values),
        rejected=sum(value in rejected_states for value in values),
        no_action=sum(value in no_action_states for value in values),
        execution_failed=sum(value in execution_failed_states for value in values),
        other_terminal=sum(
            value not in selected_states | rejected_states | no_action_states | execution_failed_states
            for value in values
        ),
    )


def _native_payloads(handoff: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    ledger = list(state["ledger_entries"])
    evidence = list(handoff["evidence_records"])
    lineage = list(handoff["lineage_records"])
    replay = list(state["replay_events"])
    valuations = list(state["valuations"])
    account = state["account_snapshot"]
    return {
        "candidate_terminal_state_ledger": state["candidate_states"],
        "orders_panel": state["orders"],
        "fills_panel": state["fills"],
        "ordered_event_ledger": replay,
        "physical_position_ledger": state["final_positions"],
        "virtual_candidate_ledger": state["virtual_allocations"],
        "cash_ledger": {"entries": _category(ledger, "CASH_FLOW"), "account": account},
        "premium_ledger": _category(ledger, "PREMIUM"),
        "cost_ledger": _category(ledger, "COST"),
        "margin_ledger": {"entries": _category(ledger, "MARGIN"), "account": account},
        "collateral_ledger": {"entries": _category(ledger, "COLLATERAL"), "account": account},
        "lifecycle_event_ledger": replay,
        "valuation_panel": valuations,
        "pnl_panel": state["pnl_snapshot"],
        "replay_checkpoint_manifest": state["replay_checkpoint"],
        "replay_expected_state": {"expected_state_sha256": state["replay_checkpoint"]["expected_state_sha256"]},
        "lineage_manifest": lineage,
        "maturity_subject_manifest": [
            {"candidate_id": row["candidate_id"], "maturity_hint": row["maturity_hint"],
             "expected_maturity_at": row.get("expected_maturity_at")}
            for row in evidence
        ],
        "executed_outcome_panel": evidence,
        "market_mark_panel": valuations,
    }


def _receipt(
    module_id: str,
    output_ids: tuple[str, ...],
    at: datetime,
    implementation_sha256: str,
) -> ModuleExecutionReceipt:
    payload = ModuleExecutionReceiptPayload(
        module_id=module_id,
        status=ModuleStatus.SUCCESS,
        started_at=at,
        completed_at=at,
        output_artifact_ids=output_ids,
        implementation_sha256=implementation_sha256,
        policy_sha256=sha256_bytes(b"P8_TO_P9_NATIVE_PUBLICATION_V1"),
    )
    return ModuleExecutionReceipt(
        payload=payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )


def _schema_type_for(value: object) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    raise ContractMismatchError("published P8 artifacts must have object or array payloads")


def _validate_supplement_cardinality(item: SupplementalArtifact, value: object) -> None:
    expected = len(value) if isinstance(value, list) else 1
    if item.record_count != expected:
        raise ContractMismatchError(
            f"supplemental record_count mismatch for {item.role}: "
            f"declared={item.record_count} actual={expected}"
        )
    declared_type = item.schema_document.get("type")
    actual_type = _schema_type_for(value)
    if declared_type != actual_type:
        raise ContractMismatchError(
            f"supplemental schema type mismatch for {item.role}: "
            f"declared={declared_type} actual={actual_type}"
        )


def publish_p8_native_handoff(
    *,
    p8_handoff: Any,
    stateful_evidence_bundle: Any,
    request: P8NativePublicationRequest,
    artifact_store: ArtifactStoreWritePort,
    supplemental_artifacts: tuple[SupplementalArtifact, ...] = (),
) -> P8NativePublication:
    handoff = _plain(model_data(p8_handoff))
    state = _plain(model_data(stateful_evidence_bundle))
    context = handoff.get("context")
    state_context = state.get("context")
    if not isinstance(context, Mapping) or context != state_context:
        raise ContractMismatchError("P8 handoff and state bundle must share the exact AuditContext")
    run_id = str(context["run_id"])
    cycle_id = str(context["cycle_id"])
    published_at = _utc(request.published_at)
    decision_time = _utc(context["decision_time"])
    if _utc(context["audit_time"]) > published_at:
        raise ContractMismatchError("published_at cannot precede the P8 audit time")
    if tuple(handoff.get("all_candidate_ids", ())) != tuple(state.get("expected_candidate_ids", ())):
        raise ContractMismatchError("P8 handoff candidates differ from state bundle candidates")

    payloads = _native_payloads(handoff, state)
    supplemental_by_role = {item.role: item for item in supplemental_artifacts}
    if len(supplemental_by_role) != len(supplemental_artifacts):
        raise ContractMismatchError("supplemental artifact roles must be unique")

    native_full_by_role: dict[str, SupplementalArtifact] = {}
    native_full = handoff.get("full_evidence")
    if native_full is not None:
        if not isinstance(native_full, Mapping):
            raise ContractMismatchError("P8 full_evidence must be a structured mapping")
        for role, raw_item in native_full.items():
            if role in supplemental_by_role:
                raise ContractMismatchError(f"duplicate native and supplemental FULL role: {role}")
            if not isinstance(raw_item, Mapping):
                raise ContractMismatchError(f"P8 full-evidence role {role} must be structured")
            value = _plain(raw_item.get("payload"))
            declared_role = str(raw_item.get("role"))
            if declared_role != role:
                raise ContractMismatchError(f"P8 full-evidence role mismatch: {role} != {declared_role}")
            native_item = SupplementalArtifact(
                role=declared_role,
                payload=value,
                schema_name=str(raw_item.get("schema_name")),
                schema_document=dict(raw_item.get("schema_document", {})),
                schema_version=str(raw_item.get("schema_version", "1.0.0")),
                producer_module_id=str(raw_item.get("producer_module_id")),
                record_count=int(raw_item.get("record_count", -1)),
                grain=tuple(raw_item.get("grain", ())),
            )
            _validate_supplement_cardinality(native_item, value)
            native_full_by_role[role] = native_item
            payloads[role] = value

    for role, item in supplemental_by_role.items():
        value = _plain(item.payload)
        _validate_supplement_cardinality(item, value)
        payloads[role] = value

    missing_native = sorted(_NATIVE_REQUIRED - set(payloads))
    if missing_native:
        raise EvidenceIncompleteError(f"P8 native publication missing required roles: {missing_native}")
    missing_full = tuple(sorted(_FULL_REQUIRED - set(payloads)))
    if request.require_full and missing_full:
        raise EvidenceIncompleteError(f"FULL P8 handoff requires supplemental roles: {missing_full}")
    mode = P8HandoffMode.FULL_V1 if not missing_full else P8HandoffMode.P8_NATIVE_0_3_LIMITED

    matrix = load_cross_phase_compatibility_matrix()
    p8_fingerprint = next(
        str(row["fingerprint_sha256"]) for row in matrix["entries"] if row["phase_id"] == "P8"
    )
    slots: list[ArtifactSlot] = []
    bindings: list[ArtifactSchemaBinding] = []
    producer_ids = {"P8.S10.M03", "P8.S10.M04"}
    for role in sorted(payloads):
        supplement = supplemental_by_role.get(role) or native_full_by_role.get(role)
        producer = supplement.producer_module_id if supplement else "P8.S10.M03"
        producer_ids.add(producer)
        schema_name = supplement.schema_name if supplement else f"p8.native.{role}"
        schema_version = supplement.schema_version if supplement else "1.0.0"
        schema_document = (
            dict(supplement.schema_document)
            if supplement
            else {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": schema_name,
                "type": _schema_type_for(payloads[role]),
                "x-artifact-role": role,
                "x-producer-module": producer,
                "x-qualified-source-fingerprint": p8_fingerprint,
                "x-profile": "P8_NATIVE_0_3",
            }
        )
        schema_sha = payload_sha256(schema_document)
        content = canonical_json_bytes(payloads[role])
        artifact_id = f"p8-{role}-{sha256_bytes(content)[:24]}"
        location = artifact_store.write_bytes(f"p8_to_p9/{artifact_id}.json", content)
        value = payloads[role]
        record_count = supplement.record_count if supplement else (len(value) if isinstance(value, list) else 1)
        grain = supplement.grain if supplement else ("record",)
        ref = ArtifactReference(
            artifact_id=artifact_id,
            artifact_type=role,
            schema_name=schema_name,
            artifact_schema_version=schema_version,
            schema_sha256=schema_sha,
            content_sha256=sha256_bytes(content),
            producer_module_id=producer,
            run_id=run_id,
            cycle_id=cycle_id,
            backtest_id=request.backtest_id,
            event_time=supplement.event_time if supplement else decision_time,
            decision_time=decision_time,
            available_at=published_at,
            computed_at=published_at,
            maturity_at=supplement.maturity_at if supplement else None,
            settlement_at=supplement.settlement_at if supplement else None,
            location=location,
            availability=Availability.AVAILABLE,
            record_count=record_count,
            grain=grain,
        )
        slots.append(ArtifactSlot(role=role, reference=ref))
        bindings.append(ArtifactSchemaBinding(
            schema_name=schema_name,
            schema_version=schema_version,
            schema_sha256=schema_sha,
            artifact_type=role,
            allowed_producer_module_ids=(producer,),
        ))

    module_bindings = tuple(
        ModuleBinding(
            module_id=module_id,
            phase_id="P8",
            subphase_id=".".join(module_id.split(".")[:2]),
        )
        for module_id in sorted(producer_ids)
    )
    module_registry = ModuleRegistrySnapshot(
        registry_version="1.0.0",
        registry_sha256=payload_sha256([item.model_dump(mode="python") for item in module_bindings]),
        modules=module_bindings,
    )
    schema_registry = ArtifactSchemaRegistrySnapshot(
        registry_version="1.0.0",
        registry_sha256=payload_sha256([item.model_dump(mode="python") for item in bindings]),
        bindings=tuple(bindings),
    )
    compatibility = ContractCompatibilityMatrix(
        matrix_version="1.0.0",
        matrix_sha256=payload_sha256({"P8_EVALUATION_HANDOFF_V1": [mode.value]}),
        entries=(ContractCompatibilityEntry(
            contract_name="P8_EVALUATION_HANDOFF_V1",
            contract_version="1.0.0",
            accepted_modes=(mode.value,),
        ),),
    )
    output_ids = tuple(slot.reference.artifact_id for slot in slots if slot.reference)
    receipts = (
        _receipt("P8.S10.M03", output_ids, published_at, p8_fingerprint),
        _receipt("P8.S10.M04", output_ids, published_at, p8_fingerprint),
    )
    limitations = () if mode is P8HandoffMode.FULL_V1 else tuple(
        ["P8 0.3 native evidence is accepted only in LIMITED mode"]
        + [f"missing FULL role: {role}" for role in missing_full]
    )
    handoff_payload = P8EvaluationHandoffPayload(
        mode=mode,
        producer_package_version=request.producer_package_version,
        run_id=run_id,
        cycle_id=cycle_id,
        backtest_id=request.backtest_id,
        published_at=published_at,
        candidate_counts=_candidate_counts(list(state["candidate_states"])),
        artifacts=tuple(slots),
        p8_module_receipts=receipts,
        limitations=limitations,
    )
    native_handoff = P8EvaluationHandoffV1(
        payload=handoff_payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(handoff_payload)),
    )
    return P8NativePublication(
        handoff=native_handoff,
        module_registry=module_registry,
        schema_registry=schema_registry,
        compatibility_matrix=compatibility,
        mode=mode,
        missing_full_roles=missing_full,
    )
