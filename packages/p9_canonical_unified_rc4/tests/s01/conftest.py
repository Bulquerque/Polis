from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from quant_pipeline.phase_09.contracts.artifacts import ArtifactReference, ArtifactSlot
from quant_pipeline.phase_09.contracts.base import Availability, EvidenceClass
from quant_pipeline.phase_09.contracts.cohort import (
    CohortPolicy,
    CohortPolicyRegistry,
    HoldoutAccessLedger,
    ResearchCommitment,
    ResearchCommitmentRegistry,
)
from quant_pipeline.phase_09.contracts.handoff import (
    CandidateTerminalCounts,
    P8EvaluationHandoffPayload,
    P8EvaluationHandoffV1,
    P8HandoffMode,
)
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256, sha256_bytes
from quant_pipeline.phase_09.contracts.lineage import (
    LineageEdge,
    LineageManifest,
    LineageManifestPayload,
    LineageNode,
    LineageRelation,
)
from quant_pipeline.phase_09.contracts.maturity import (
    LifecycleStatus,
    MaturityBasis,
    MaturitySubject,
    MaturitySubjectManifest,
    MaturitySubjectManifestPayload,
    OutcomeMaturityPolicy,
    OutcomeMaturityPolicyRegistry,
)
from quant_pipeline.phase_09.contracts.outcomes import (
    ExecutedOutcomePanel,
    ExecutedOutcomeRecord,
    MarkingPolicy,
    MarketMarkPanel,
)
from quant_pipeline.phase_09.contracts.registry import (
    ArtifactSchemaBinding,
    ArtifactSchemaRegistrySnapshot,
    ContractCompatibilityEntry,
    ContractCompatibilityMatrix,
    ModuleBinding,
    ModuleRegistrySnapshot,
)
from quant_pipeline.phase_09.contracts.replay import (
    OrderedEventLedger,
    OrderedEventLedgerPayload,
    PositionState,
    ReplayCheckpoint,
    ReplayCheckpointPayload,
    ReplayEvent,
    ReplayEventType,
    ReplayPolicy,
    ReplayState,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import FULL_REQUIRED_ROLES
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m02_lineage_resolver import LineageResolutionPolicy
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import InMemoryArtifactStore

ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class FullFixture:
    store: InMemoryArtifactStore
    handoff: P8EvaluationHandoffV1
    compatibility: ContractCompatibilityMatrix
    module_registry: ModuleRegistrySnapshot
    schema_registry: ArtifactSchemaRegistrySnapshot
    lineage_policy: LineageResolutionPolicy
    replay_policy: ReplayPolicy
    maturity_policies: OutcomeMaturityPolicyRegistry
    commitments: ResearchCommitmentRegistry
    cohort_policies: CohortPolicyRegistry
    holdout_access: HoldoutAccessLedger
    evaluation_as_of: datetime
    clock: FixedClock


def model_bytes(model) -> bytes:
    return model.model_dump_json().encode("utf-8")


def envelope(payload) -> IntegrityEnvelope:
    return IntegrityEnvelope(payload_sha256=payload_sha256(payload))


def _artifact_ref(
    *,
    store: InMemoryArtifactStore,
    role: str,
    payload: bytes,
    producer: str,
    run_id: str,
    cycle_id: str,
    backtest_id: str,
    timestamp: datetime,
    schema_version: str = "1.0.0",
) -> ArtifactReference:
    location = store.write_bytes(f"full/{role}.json", payload)
    return ArtifactReference(
        artifact_id=f"artifact-{role}",
        artifact_type=role,
        schema_name=role,
        artifact_schema_version=schema_version,
        schema_sha256=sha256_bytes(f"schema:{role}:{schema_version}".encode()),
        content_sha256=sha256_bytes(payload),
        producer_module_id=producer,
        run_id=run_id,
        cycle_id=cycle_id,
        backtest_id=backtest_id,
        event_time=timestamp,
        decision_time=timestamp,
        available_at=timestamp,
        computed_at=timestamp,
        location=location,
        availability=Availability.AVAILABLE,
        record_count=1,
        grain=("artifact_id",),
    )


def build_full_fixture() -> FullFixture:
    store = InMemoryArtifactStore()
    t0 = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=2)
    run_id = "run-1"
    cycle_id = "cycle-1"
    backtest_id = "backtest-1"

    producer_modules = (
        "P2.S1.M01",
        "P4.S1.M01",
        "P5.S1.M01",
        "P6.S1.M01",
        "P7.S1.M01",
        "P8.S5.M03",
    )
    module_registry = ModuleRegistrySnapshot(
        registry_version="1.0.0",
        registry_sha256=sha256_bytes(b"module-registry"),
        modules=tuple(
            ModuleBinding(
                module_id=module_id,
                phase_id=module_id.split(".")[0],
                subphase_id=".".join(module_id.split(".")[:2]),
            )
            for module_id in producer_modules
        ),
    )

    lineage_nodes = []
    for index, module_id in enumerate(producer_modules):
        phase_id = module_id.split(".")[0]
        payload = json.dumps({"phase": phase_id, "index": index}, sort_keys=True).encode()
        location = store.write_bytes(f"lineage/{phase_id}.json", payload)
        artifact = ArtifactReference(
            artifact_id=f"lineage-artifact-{phase_id}",
            artifact_type=f"{phase_id.lower()}_evidence",
            schema_name=f"{phase_id.lower()}_evidence",
            artifact_schema_version="1.0.0",
            schema_sha256=sha256_bytes(f"schema:{phase_id}".encode()),
            content_sha256=sha256_bytes(payload),
            producer_module_id=module_id,
            run_id=run_id,
            cycle_id=cycle_id,
            backtest_id=backtest_id,
            event_time=t0,
            decision_time=t0,
            available_at=t0,
            computed_at=t0,
            location=location,
            availability=Availability.AVAILABLE,
            record_count=1,
            grain=("phase",),
        )
        lineage_nodes.append(
            LineageNode(
                node_id=f"node-{phase_id}",
                phase_id=phase_id,
                entity_type="ARTIFACT",
                artifact=artifact,
                generated_at=t0,
            )
        )
    lineage_edges = tuple(
        LineageEdge(
            edge_id=f"edge-{left.phase_id}-{right.phase_id}",
            parent_node_id=left.node_id,
            child_node_id=right.node_id,
            relation=LineageRelation.DERIVED_FROM,
            occurred_at=t0,
        )
        for left, right in zip(lineage_nodes, lineage_nodes[1:])
    )
    lineage_payload = LineageManifestPayload(
        manifest_id="lineage-manifest-1",
        cycle_id=cycle_id,
        nodes=tuple(lineage_nodes),
        edges=lineage_edges,
        root_node_ids=(lineage_nodes[0].node_id,),
    )
    lineage_manifest = LineageManifest(payload=lineage_payload, integrity=envelope(lineage_payload))

    checkpoint_payload = ReplayCheckpointPayload(
        checkpoint_id="checkpoint-1",
        last_sequence=-1,
        state=ReplayState(as_of=t0, cash=Decimal("1000")),
    )
    checkpoint = ReplayCheckpoint(payload=checkpoint_payload, integrity=envelope(checkpoint_payload))
    event_payload = OrderedEventLedgerPayload(
        ledger_id="event-ledger-1",
        events=(
            ReplayEvent(
                event_id="event-0",
                sequence=0,
                occurred_at=t0 + timedelta(minutes=1),
                event_type=ReplayEventType.FILL,
                fill_id="fill-1",
                position_id="position-1",
                candidate_id="candidate-1",
                instrument_id="instrument-1",
                quantity_delta=Decimal("1"),
                price=Decimal("100"),
                fee_amount=Decimal("1"),
            ),
            ReplayEvent(
                event_id="event-1",
                sequence=1,
                occurred_at=t0 + timedelta(minutes=2),
                event_type=ReplayEventType.MARK,
                position_id="position-1",
                mark_price=Decimal("110"),
            ),
            ReplayEvent(
                event_id="event-2",
                sequence=2,
                occurred_at=t0 + timedelta(minutes=3),
                event_type=ReplayEventType.MARGIN_UPDATE,
                margin_used=Decimal("20"),
            ),
        ),
    )
    event_ledger = OrderedEventLedger(payload=event_payload, integrity=envelope(event_payload))
    expected_state = ReplayState(
        as_of=t0 + timedelta(minutes=3),
        cash=Decimal("899"),
        margin_used=Decimal("20"),
        fees_paid=Decimal("1"),
        positions=(
            PositionState(
                position_id="position-1",
                candidate_id="candidate-1",
                instrument_id="instrument-1",
                quantity=Decimal("1"),
                mark_price=Decimal("110"),
            ),
        ),
    )

    subject = MaturitySubject(
        subject_id="subject-1",
        target_type="PRIMARY",
        instrument_id="instrument-1",
        contract_key="contract-1",
        decision_time=t0,
        horizon_end=t1,
        close_time=t1,
        observation_end=t1,
        data_available_at=t1,
        lifecycle_status=LifecycleStatus.CLOSED,
        reference_price=Decimal("100"),
        quantity=Decimal("1"),
        contract_multiplier=Decimal("1"),
    )
    subject_payload = MaturitySubjectManifestPayload(
        manifest_id="maturity-manifest-1",
        subjects=(subject,),
    )
    subject_manifest = MaturitySubjectManifest(
        payload=subject_payload,
        integrity=envelope(subject_payload),
    )
    executed_panel = ExecutedOutcomePanel(
        records=(
            ExecutedOutcomeRecord(
                subject_id="subject-1",
                realized_pnl=Decimal("10"),
                realized_return=Decimal("0.1"),
                closed_at=t1,
                source_artifact_id="fills-panel-1",
                source_sha256=sha256_bytes(b"fills-panel-1"),
            ),
        )
    )
    mark_panel = MarketMarkPanel(records=())
    marking_policy = MarkingPolicy(
        policy_id="marking-policy-1",
        max_staleness_seconds=86_400,
        allow_model_marks=False,
    )

    special_payloads = {
        "lineage_manifest": model_bytes(lineage_manifest),
        "replay_checkpoint_manifest": model_bytes(checkpoint),
        "ordered_event_ledger": model_bytes(event_ledger),
        "replay_expected_state": model_bytes(expected_state),
        "maturity_subject_manifest": model_bytes(subject_manifest),
        "executed_outcome_panel": model_bytes(executed_panel),
        "market_mark_panel": model_bytes(mark_panel),
        "marking_policy_snapshot": model_bytes(marking_policy),
    }
    refs: dict[str, ArtifactReference] = {}
    for role in sorted(FULL_REQUIRED_ROLES):
        payload = special_payloads.get(role, json.dumps({"role": role}, sort_keys=True).encode())
        refs[role] = _artifact_ref(
            store=store,
            role=role,
            payload=payload,
            producer="P8.S5.M03",
            run_id=run_id,
            cycle_id=cycle_id,
            backtest_id=backtest_id,
            timestamp=t2,
        )

    schema_registry = ArtifactSchemaRegistrySnapshot(
        registry_version="1.0.0",
        registry_sha256=sha256_bytes(b"schema-registry"),
        bindings=tuple(
            ArtifactSchemaBinding(
                schema_name=role,
                schema_version="1.0.0",
                schema_sha256=ref.schema_sha256,
                artifact_type=role,
                allowed_producer_module_ids=("P8.S5.M03",),
            )
            for role, ref in sorted(refs.items())
        ),
    )
    compatibility = ContractCompatibilityMatrix(
        matrix_version="1.0.0",
        matrix_sha256=sha256_bytes(b"compatibility"),
        entries=(
            ContractCompatibilityEntry(
                contract_name="P8_EVALUATION_HANDOFF_V1",
                contract_version="1.0.0",
                accepted_modes=("FULL_V1", "LEGACY_RC4_1_LIMITED"),
            ),
        ),
    )
    handoff_payload = P8EvaluationHandoffPayload(
        mode=P8HandoffMode.FULL_V1,
        producer_package_version="P8-NEW-1.0.0",
        run_id=run_id,
        cycle_id=cycle_id,
        backtest_id=backtest_id,
        published_at=t2,
        candidate_counts=CandidateTerminalCounts(
            received=1,
            selected=1,
            rejected=0,
            no_action=0,
            execution_failed=0,
            other_terminal=0,
        ),
        artifacts=tuple(ArtifactSlot(role=role, reference=ref) for role, ref in sorted(refs.items())),
        p8_module_receipts=(),
    )
    handoff = P8EvaluationHandoffV1(payload=handoff_payload, integrity=envelope(handoff_payload))

    maturity_policies = OutcomeMaturityPolicyRegistry(
        policies=(
            OutcomeMaturityPolicy(
                policy_id="maturity-primary-1",
                metric_family="primary",
                target_type="PRIMARY",
                basis=MaturityBasis.HORIZON,
            ),
        )
    )
    commitment_payload = {
        "commitment_id": "commitment-1",
        "created_at": t0 - timedelta(days=2),
        "effective_from": t0 - timedelta(days=1),
        "metric_ids": ("primary",),
        "cohort_policy_id": "cohort-policy-1",
        "holdout_dataset_ids": ("holdout-1",),
    }
    commitment = ResearchCommitment(
        **commitment_payload,
        commitment_sha256=payload_sha256(commitment_payload),
    )
    commitments = ResearchCommitmentRegistry(commitments=(commitment,))
    cohort_policies = CohortPolicyRegistry(
        policies=(
            CohortPolicy(
                policy_id="cohort-policy-1",
                allowed_target_types=("PRIMARY",),
                allowed_evidence_classes=(EvidenceClass.FACTUAL_EXECUTED,),
                minimum_sample=1,
                require_complete_lineage=True,
            ),
        )
    )
    return FullFixture(
        store=store,
        handoff=handoff,
        compatibility=compatibility,
        module_registry=module_registry,
        schema_registry=schema_registry,
        lineage_policy=LineageResolutionPolicy(),
        replay_policy=ReplayPolicy(),
        maturity_policies=maturity_policies,
        commitments=commitments,
        cohort_policies=cohort_policies,
        holdout_access=HoldoutAccessLedger(),
        evaluation_as_of=t2,
        clock=FixedClock(t2),
    )


@pytest.fixture
def full_fixture() -> FullFixture:
    return build_full_fixture()
