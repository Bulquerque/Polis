from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from quant_pipeline.phase_09.compatibility.models import P8NativePublicationRequest
from quant_pipeline.phase_09.compatibility.p8_ingress import publish_p8_native_handoff
from quant_pipeline.phase_09.contracts.handoff import P8HandoffMode
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import InMemoryArtifactStore


def _roots() -> tuple[Path, Path]:
    p9_root = Path(__file__).resolve().parents[2]
    return p9_root, p9_root.parent / "P8_INTEGRATED_RC3"


def _schema(title: str, kind: str = "object") -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": kind,
        "additionalProperties": True,
    }


def _artifact(model, role: str, payload: dict[str, object], producer: str):
    return model(
        role=role,
        payload=payload,
        schema_name=f"p8.full.{role}",
        schema_document=_schema(f"p8.full.{role}"),
        producer_module_id=producer,
        record_count=1,
        grain=("portfolio",),
    )


def test_p8_native_full_evidence_is_published_without_external_supplements(monkeypatch):
    _, p8_root = _roots()
    monkeypatch.syspath_prepend(str(p8_root / "src"))
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_handoff import (
        P9EvaluationHandoff,
        P9FullEvidenceArtifact,
        P9FullEvidenceBundle,
    )
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import (
        StatefulEvidenceBundle,
    )

    state = StatefulEvidenceBundle.model_validate_json(
        (p8_root / "tests/agents/subphases/s10/fixtures/input/stateful_evidence_bundle.json").read_text(),
        strict=False,
    )
    result = json.loads(
        (p8_root / "tests/agents/subphases/s10/fixtures/expected/normal_result.json").read_text()
    )
    handoff = P9EvaluationHandoff.model_validate(result["p9_handoff"], strict=False)
    full = P9FullEvidenceBundle(
        nav_panel=_artifact(P9FullEvidenceArtifact, "nav_panel", {
            "initial_nav": str(state.account_snapshot.initial_nav),
            "final_cash": str(state.account_snapshot.final_cash),
            "valuation_count": len(state.valuations),
        }, "P8.S8.M05"),
        exposure_panel=_artifact(P9FullEvidenceArtifact, "exposure_panel", {
            "positions": [row.model_dump(mode="json") for row in state.final_positions],
            "virtual_allocations": [row.model_dump(mode="json") for row in state.virtual_allocations],
        }, "P8.S8.M03"),
        drawdown_panel=_artifact(P9FullEvidenceArtifact, "drawdown_panel", {
            "method": "P8_STATEFUL_EQUITY_PATH",
            "status": "AVAILABLE",
        }, "P8.S8.M05"),
        optimizer_decision_trace=_artifact(P9FullEvidenceArtifact, "optimizer_decision_trace", {
            "trace_id": "optimizer-trace-fixture",
            "status": "COMPLETED",
        }, "P8.S5.M07"),
        portfolio_decision_panel=_artifact(P9FullEvidenceArtifact, "portfolio_decision_panel", {
            "candidate_states": [row.model_dump(mode="json") for row in state.candidate_states],
        }, "P8.S6.M06"),
        marking_policy_snapshot=_artifact(P9FullEvidenceArtifact, "marking_policy_snapshot", {
            "marks": [row.model_dump(mode="json") for row in state.valuations],
            "policy": "P8_MARKING_POLICY_V1",
        }, "P8.S8.M05"),
    )
    handoff = handoff.model_copy(update={"full_evidence": full})
    store = InMemoryArtifactStore()
    publication = publish_p8_native_handoff(
        p8_handoff=handoff,
        stateful_evidence_bundle=state,
        request=P8NativePublicationRequest(
            backtest_id="backtest-p8-native-full",
            producer_package_version="0.3.0rc3",
            published_at=datetime(2026, 8, 4, 17, tzinfo=UTC),
            require_full=True,
        ),
        artifact_store=store,
    )
    assert publication.mode is P8HandoffMode.FULL_V1
    assert publication.missing_full_roles == ()
    roles = {slot.role for slot in publication.handoff.payload.artifacts}
    assert {
        "nav_panel", "exposure_panel", "drawdown_panel", "optimizer_decision_trace",
        "portfolio_decision_panel", "marking_policy_snapshot",
    }.issubset(roles)
    slots = {slot.role: slot.reference for slot in publication.handoff.payload.artifacts}
    assert slots["optimizer_decision_trace"].producer_module_id == "P8.S5.M07"
    assert slots["portfolio_decision_panel"].producer_module_id == "P8.S6.M06"
    assert slots["nav_panel"].producer_module_id == "P8.S8.M05"
    assert slots["optimizer_decision_trace"].schema_name == "p8.full.optimizer_decision_trace"
