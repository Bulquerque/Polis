from __future__ import annotations

from pydantic import BaseModel

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.inputs import RiskLifecycleContextBundle


def parse_json_artifact[ModelT: BaseModel](model_type: type[ModelT], payload: str | bytes) -> ModelT:
    """Coerce JSON arrays/timestamps only at the explicit external boundary."""
    return model_type.model_validate_json(payload, strict=False)


def parse_risk_bundle_json(payload: str | bytes) -> DecisionReadyRiskBundle:
    return parse_json_artifact(DecisionReadyRiskBundle, payload)


def parse_lifecycle_context_json(payload: str | bytes) -> RiskLifecycleContextBundle:
    return parse_json_artifact(RiskLifecycleContextBundle, payload)
