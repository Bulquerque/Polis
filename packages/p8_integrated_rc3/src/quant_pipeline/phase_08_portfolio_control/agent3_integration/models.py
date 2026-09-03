from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import ArtifactEnvelope
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.artifacts import ExecutionAuthorizationBundle


class Agent3IntegratedPayload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        validate_default=True,
        revalidate_instances="always",
        allow_inf_nan=False,
    )

    s5_result: S5ResultBundle
    s6_authorization: ExecutionAuthorizationBundle
    integration_receipts: tuple[str, ...]

    @model_validator(mode="after")
    def validate_chain(self) -> "Agent3IntegratedPayload":
        s5 = self.s5_result
        s6 = self.s6_authorization
        if s5.envelope.run_id != s6.envelope.run_id:
            raise ValueError("S5/S6 run ID mismatch")
        if s5.envelope.cycle_id != s6.envelope.cycle_id:
            raise ValueError("S5/S6 cycle ID mismatch")
        if s5.envelope.decision_time != s6.envelope.decision_time:
            raise ValueError("S5/S6 decision time mismatch")
        if s5.payload.mpc_plan.decision_snapshot_hash != s6.payload.decision_snapshot_hash:
            raise ValueError("S5/S6 decision snapshot mismatch")
        if s6.envelope.available_at < s5.envelope.available_at:
            raise ValueError("S6 result cannot predate S5 result")
        return self


class Agent3IntegratedBundle(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        validate_default=True,
        revalidate_instances="always",
        allow_inf_nan=False,
    )

    envelope: ArtifactEnvelope
    payload: Agent3IntegratedPayload
