"""Build the native P8→P9 FULL evidence publication from authoritative P8 outputs.

The builder performs no economic reconstruction.  Each artifact is a lossless
projection of a typed output already produced by P8 S4/S5/S6/S8.  When one of
those authorities is unavailable, callers must keep the handoff in LIMITED
mode rather than manufacture a placeholder.
"""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import (
    S5ResultBundle,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
    DecisionReadyRiskBundle,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.artifacts import (
    ExecutionAuthorizationBundle,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.input_models import (
    S8InputBundle,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.runner import (
    S8Result,
)

from .models_handoff import P9FullEvidenceArtifact, P9FullEvidenceBundle

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _object_artifact(
    *,
    role: str,
    value: BaseModel,
    schema_name: str,
    producer_module_id: str,
) -> P9FullEvidenceArtifact:
    schema = value.__class__.model_json_schema(mode="validation")
    schema = {**schema, "$schema": _DRAFT, "title": schema_name, "type": "object"}
    return P9FullEvidenceArtifact(
        role=role,
        payload=value.model_dump(mode="json"),
        schema_name=schema_name,
        schema_document=schema,
        producer_module_id=producer_module_id,
        record_count=1,
        grain=(),
    )


def _row_artifact(
    *,
    role: str,
    rows: tuple[BaseModel, ...],
    row_model: Type[BaseModel],
    schema_name: str,
    producer_module_id: str,
    grain: tuple[str, ...],
) -> P9FullEvidenceArtifact:
    item_schema: dict[str, Any] = row_model.model_json_schema(mode="validation")
    definitions = item_schema.pop("$defs", {})
    schema = {
        "$schema": _DRAFT,
        "title": schema_name,
        "type": "array",
        "items": item_schema,
        **({"$defs": definitions} if definitions else {}),
    }
    return P9FullEvidenceArtifact(
        role=role,
        payload=tuple(item.model_dump(mode="json") for item in rows),
        schema_name=schema_name,
        schema_document=schema,
        producer_module_id=producer_module_id,
        record_count=len(rows),
        grain=grain,
    )


def build_native_p9_full_evidence(
    *,
    risk_bundle: DecisionReadyRiskBundle,
    optimization_result: S5ResultBundle,
    authorization_result: ExecutionAuthorizationBundle,
    s8_input: S8InputBundle,
    s8_result: S8Result,
) -> P9FullEvidenceBundle:
    """Create all six FULL roles from the P8 objects that own those facts.

    This function deliberately requires every authority.  It cannot be called
    with partial evidence and never fills a missing role with synthetic data.
    """
    return P9FullEvidenceBundle(
        nav_panel=_object_artifact(
            role="nav_panel",
            value=s8_result.valuation.nav,
            schema_name="P8NativeNAVPanelV1",
            producer_module_id="P8.S8.M05",
        ),
        exposure_panel=_row_artifact(
            role="exposure_panel",
            rows=tuple(risk_bundle.payload.candidates),
            row_model=type(risk_bundle.payload.candidates[0]) if risk_bundle.payload.candidates else _candidate_model(),
            schema_name="P8NativeExposurePanelV1",
            producer_module_id="P8.S4.M07",
            grain=("candidate_id",),
        ),
        drawdown_panel=_object_artifact(
            role="drawdown_panel",
            value=_require_drawdown(s8_result),
            schema_name="P8NativeDrawdownPanelV1",
            producer_module_id="P8.S8.M05",
        ),
        optimizer_decision_trace=_object_artifact(
            role="optimizer_decision_trace",
            value=optimization_result.payload,
            schema_name="P8NativeOptimizerDecisionTraceV1",
            producer_module_id="P8.S5.M07",
        ),
        portfolio_decision_panel=_object_artifact(
            role="portfolio_decision_panel",
            value=authorization_result.payload,
            schema_name="P8NativePortfolioDecisionPanelV1",
            producer_module_id="P8.S6.M07",
        ),
        marking_policy_snapshot=_object_artifact(
            role="marking_policy_snapshot",
            value=s8_input.policies.mark_selection,
            schema_name="P8NativeMarkingPolicySnapshotV1",
            producer_module_id="P8.S8.M05",
        ),
    )


def _require_drawdown(result: S8Result) -> BaseModel:
    if result.valuation.drawdown is None:
        raise ValueError("P8→P9 FULL requires a drawdown record; keep the handoff LIMITED")
    return result.valuation.drawdown


def _candidate_model() -> Type[BaseModel]:
    # The type is imported lazily to keep this helper valid for an empty panel;
    # an empty panel remains a valid array with a closed item schema.
    from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import (
        CandidateRiskInput,
    )

    return CandidateRiskInput
