from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from quant_pipeline.phase_09.contracts.artifacts import (
    ArtifactAbsenceState,
    ArtifactReference,
    ArtifactSlot,
)
from quant_pipeline.phase_09.contracts.base import Availability
from quant_pipeline.phase_09.contracts.handoff import (
    CandidateTerminalCounts,
    P8EvaluationHandoffPayload,
    P8EvaluationHandoffV1,
    P8HandoffMode,
)
from quant_pipeline.phase_09.contracts.integrity import (
    IntegrityEnvelope,
    payload_sha256,
    sha256_bytes,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import ArtifactStoreWritePort

LEGACY_ROLES = (
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
)


@dataclass(frozen=True, slots=True)
class LegacyArtifactSpec:
    schema_name: str
    schema_version: str
    schema_sha256: str
    producer_module_id: str
    artifact_type: str
    grain: tuple[str, ...] = ()


class LegacyP8RC41Adapter:
    """Maps legacy P8 RC4.1 outputs into an explicitly LIMITED handoff.

    The adapter never manufactures replay, lineage, maturity, or mark evidence. Missing
    legacy artifacts become explicit absence slots and the resulting handoff cannot be
    upgraded to FULL_V1.
    """

    def __init__(self, store: ArtifactStoreWritePort) -> None:
        self._store = store

    def adapt(
        self,
        *,
        artifact_payloads: Mapping[str, bytes],
        artifact_specs: Mapping[str, LegacyArtifactSpec],
        run_id: str,
        cycle_id: str,
        backtest_id: str,
        published_at: datetime,
        producer_package_version: str = "V14.1-RC4.1",
    ) -> P8EvaluationHandoffV1:
        slots: list[ArtifactSlot] = []
        for role in LEGACY_ROLES:
            payload = artifact_payloads.get(role)
            spec = artifact_specs.get(role)
            if payload is None or spec is None:
                slots.append(
                    ArtifactSlot(
                        role=role,
                        absence_state=ArtifactAbsenceState.NOT_PRODUCED,
                        reason_codes=("P9_S1_HANDOFF_REQUIRED_ARTIFACT_MISSING",),
                    )
                )
                continue
            location = self._store.write_bytes(f"legacy/{role}.json", payload)
            record_count = self._record_count(payload)
            slots.append(
                ArtifactSlot(
                    role=role,
                    reference=ArtifactReference(
                        artifact_id=f"legacy-{role}-{sha256_bytes(payload)[:12]}",
                        artifact_type=spec.artifact_type,
                        schema_name=spec.schema_name,
                        artifact_schema_version=spec.schema_version,
                        schema_sha256=spec.schema_sha256,
                        content_sha256=sha256_bytes(payload),
                        producer_module_id=spec.producer_module_id,
                        run_id=run_id,
                        cycle_id=cycle_id,
                        backtest_id=backtest_id,
                        available_at=published_at,
                        computed_at=published_at,
                        location=location,
                        availability=Availability.LIMITED,
                        record_count=record_count,
                        grain=spec.grain,
                    ),
                )
            )
        counts = self._candidate_counts(artifact_payloads)
        payload = P8EvaluationHandoffPayload(
            mode=P8HandoffMode.LEGACY_RC4_1_LIMITED,
            producer_package_version=producer_package_version,
            run_id=run_id,
            cycle_id=cycle_id,
            backtest_id=backtest_id,
            published_at=published_at,
            candidate_counts=counts,
            artifacts=tuple(slots),
            p8_module_receipts=(),
            limitations=(
                "legacy P8 lacks transitive lineage",
                "legacy P8 lacks an ordered event stream and replay checkpoint",
                "legacy P8 lacks outcome maturity and mark-quality evidence",
                "legacy P8 is migration-only and cannot support production promotion",
            ),
        )
        return P8EvaluationHandoffV1(
            payload=payload,
            integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
        )

    @staticmethod
    def _record_count(payload: bytes) -> int:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return 0
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for key in ("records", "rows", "data"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    return len(candidate)
            return 1
        return 0

    @classmethod
    def _candidate_counts(cls, payloads: Mapping[str, bytes]) -> CandidateTerminalCounts:
        ranking = cls._json_records(payloads.get("ranking_context_snapshot"))
        fills = cls._json_records(payloads.get("fills_panel"))
        candidates = {
            str(item.get("candidate_id"))
            for item in ranking
            if item.get("candidate_id") is not None
        }
        filled = {
            str(item.get("candidate_id"))
            for item in fills
            if item.get("candidate_id") is not None
            and str(item.get("fill_status", "")).upper() not in {"REJECTED", "FAILED"}
        }
        received = len(candidates)
        selected = len(candidates & filled)
        no_action = 1 if received == 0 else 0
        if no_action:
            received = 1
        rejected = max(received - selected - no_action, 0)
        return CandidateTerminalCounts(
            received=received,
            selected=selected,
            rejected=rejected,
            no_action=no_action,
            execution_failed=0,
            other_terminal=0,
        )

    @staticmethod
    def _json_records(payload: bytes | None) -> list[dict[str, object]]:
        if payload is None:
            return []
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for key in ("records", "rows", "data"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    return [item for item in candidate if isinstance(item, dict)]
            return [value]
        return []
