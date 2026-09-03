"""Candidate shape, unit economics, positions, and factor semantics."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .base import ArtifactRef, StrictModel
from .enums import OptionType, ShockKind


class FactorDefinition(StrictModel):
    factor_id: str = Field(min_length=1)
    shock_kind: ShockKind
    unit: str = Field(min_length=1)


class GreekVector(StrictModel):
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    rho: float | None = None
    vanna: float | None = None
    volga: float | None = None
    charm: float | None = None
    unit_description: str = "PER_CANDIDATE_UNIT"


class LinearLeg(StrictModel):
    kind: Literal["LINEAR"] = "LINEAR"
    leg_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    factor_id: str = Field(min_length=1)
    quantity_per_unit: float
    pnl_per_factor_unit: float
    currency: str = Field(min_length=3, max_length=3)
    greeks_per_unit: GreekVector | None = None

    @model_validator(mode="after")
    def validate_nonzero(self) -> "LinearLeg":
        if self.quantity_per_unit == 0.0:
            raise ValueError("quantity_per_unit must be nonzero")
        return self


class EuropeanOptionLeg(StrictModel):
    kind: Literal["EUROPEAN_OPTION"] = "EUROPEAN_OPTION"
    leg_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    underlying_factor_id: str = Field(min_length=1)
    volatility_factor_id: str | None = None
    rate_factor_id: str | None = None
    option_type: OptionType
    quantity_per_unit: float
    spot: float = Field(gt=0.0)
    strike: float = Field(gt=0.0)
    volatility: float = Field(gt=0.0)
    risk_free_rate: float
    dividend_yield: float = 0.0
    time_to_expiry_years: float = Field(gt=0.0)
    contract_multiplier: float = Field(default=1.0, gt=0.0)
    currency: str = Field(min_length=3, max_length=3)
    provided_greeks_per_unit: GreekVector | None = None

    @model_validator(mode="after")
    def validate_nonzero(self) -> "EuropeanOptionLeg":
        if self.quantity_per_unit == 0.0:
            raise ValueError("quantity_per_unit must be nonzero")
        return self


CandidateLeg = Annotated[LinearLeg | EuropeanOptionLeg, Field(discriminator="kind")]


class CandidateEconomicPackage(StrictModel):
    candidate_id: str = Field(min_length=1)
    canonical_candidate_id: str = Field(min_length=1)
    strategy_family: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    unit_definition: str = Field(min_length=1)
    legs: tuple[CandidateLeg, ...] = Field(min_length=1)
    entry_cash_flow_per_unit: float | None = None
    entry_cash_flow_status: Literal[
        "QUALIFIED", "DEGRADED", "RESERVED", "UNAVAILABLE", "REJECTED"
    ] = "UNAVAILABLE"
    gross_notional_per_unit: float | None = Field(default=None, gt=0.0)
    maximum_loss_per_unit: float | None = Field(default=None, ge=0.0)
    maximum_loss_proof_status: Literal["PROVEN", "DEGRADED", "UNAVAILABLE"] = "UNAVAILABLE"
    margin_offset_group: str | None = None
    required_capabilities: tuple[str, ...] = ()
    source_ref: ArtifactRef

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_entry_cash_flow_status(cls, value: Any) -> Any:
        if isinstance(value, dict) and "entry_cash_flow_status" not in value:
            value = dict(value)
            value["entry_cash_flow_status"] = (
                "QUALIFIED"
                if value.get("entry_cash_flow_per_unit") is not None
                else "UNAVAILABLE"
            )
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> "CandidateEconomicPackage":
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            raise ValueError("leg_id must be unique within candidate")
        if any(leg.currency != self.currency for leg in self.legs):
            raise ValueError("all candidate legs must share candidate currency")
        usable = {"QUALIFIED", "DEGRADED"}
        if self.entry_cash_flow_status in usable and self.entry_cash_flow_per_unit is None:
            raise ValueError("qualified/degraded entry cash flow requires a value")
        if self.entry_cash_flow_status not in usable and self.entry_cash_flow_per_unit is not None:
            raise ValueError("unqualified entry cash flow cannot carry a numeric value")
        return self


class CandidatePosition(StrictModel):
    candidate_id: str
    units: float


class PhysicalPosition(StrictModel):
    instrument_id: str
    quantity: float
    attribution_status: Literal["ATTRIBUTED", "EXTERNAL_EXPLICIT"] = "ATTRIBUTED"
