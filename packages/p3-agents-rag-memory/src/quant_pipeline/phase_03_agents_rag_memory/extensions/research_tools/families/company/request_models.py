"""Strict request contracts for company fundamentals operations."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel, NonEmptyStr

from .model_base import CompanyMode, PositiveFloat, PositiveInt, ValuationMethod


class CompanyBaseRequest(ContractModel):
    entity_id: NonEmptyStr
    research_mode: CompanyMode = CompanyMode.QUICK_CHECK


class GetProfileRequest(CompanyBaseRequest):
    view_id: NonEmptyStr = "company_profile"
    include_instruments: bool = True
    include_segments: bool = True


class GetFinancialStatementsRequest(CompanyBaseRequest):
    view_id: NonEmptyStr = "financial_statements"
    statement_types: tuple[NonEmptyStr, ...] = ("INCOME", "BALANCE", "CASH_FLOW")
    periods: Annotated[int, Field(ge=1, le=20)] = 5
    include_restated_versions: bool = True


class GetFundamentalSnapshotRequest(CompanyBaseRequest):
    view_id: NonEmptyStr = "financial_statements"
    periods: Annotated[int, Field(ge=2, le=20)] = 5
    formula_ids: tuple[NonEmptyStr, ...] = (
        "revenue_growth", "operating_margin", "cash_conversion", "net_debt_to_ebitda"
    )


class GetGuidanceRequest(CompanyBaseRequest):
    view_id: NonEmptyStr = "company_guidance"
    metric_ids: tuple[NonEmptyStr, ...] = ()
    include_withdrawn: bool = False


class GetCapitalAllocationRequest(CompanyBaseRequest):
    statement_view_id: NonEmptyStr = "financial_statements"
    corporate_action_view_id: NonEmptyStr = "corporate_actions"
    periods: Annotated[int, Field(ge=1, le=20)] = 5


class GetPeersRequest(CompanyBaseRequest):
    view_id: NonEmptyStr = "company_peers"
    maximum_peers: Annotated[int, Field(ge=1, le=50)] = 10
    authority_classes: tuple[NonEmptyStr, ...] = ("DOCUMENTED", "CANONICAL")


class DcfAssumptions(ContractModel):
    base_free_cash_flow: float
    growth_rates: tuple[float, ...]
    discount_rate: Annotated[float, Field(gt=0.0, lt=1.0)]
    terminal_growth_rate: Annotated[float, Field(ge=-0.2, lt=0.2)]
    net_debt: float = 0.0
    shares_outstanding: PositiveFloat = 1.0

    @model_validator(mode="after")
    def terminal_below_discount(self) -> "DcfAssumptions":
        if self.terminal_growth_rate >= self.discount_rate:
            raise ValueError("terminal_growth_rate must be below discount_rate")
        if not self.growth_rates:
            raise ValueError("growth_rates cannot be empty")
        return self


class ReverseDcfAssumptions(ContractModel):
    market_price: PositiveFloat
    base_free_cash_flow: float
    discount_rate: Annotated[float, Field(gt=0.0, lt=1.0)]
    terminal_growth_rate: Annotated[float, Field(ge=-0.2, lt=0.2)]
    forecast_years: Annotated[int, Field(ge=1, le=20)] = 5
    net_debt: float = 0.0
    shares_outstanding: PositiveFloat = 1.0
    lower_growth: float = -0.5
    upper_growth: float = 1.0
    iterations: Annotated[int, Field(ge=10, le=200)] = 80

    @model_validator(mode="after")
    def bounds_valid(self) -> "ReverseDcfAssumptions":
        if self.terminal_growth_rate >= self.discount_rate:
            raise ValueError("terminal_growth_rate must be below discount_rate")
        if self.lower_growth >= self.upper_growth:
            raise ValueError("lower_growth must be below upper_growth")
        return self


class CalculateValuationRequest(CompanyBaseRequest):
    method: ValuationMethod = ValuationMethod.SCENARIO_DCF
    fundamentals_view_id: NonEmptyStr = "financial_statements"
    peers_view_id: NonEmptyStr = "company_peers"
    market_view_id: NonEmptyStr = "market_prices"
    multiple_name: NonEmptyStr = "EV_EBITDA"
    explicit_multiple: float | None = None
    metric_value: float | None = None
    dcf: DcfAssumptions | None = None
    reverse_dcf: ReverseDcfAssumptions | None = None

    @model_validator(mode="after")
    def method_inputs_match(self) -> "CalculateValuationRequest":
        if self.method is ValuationMethod.SCENARIO_DCF and self.dcf is None:
            raise ValueError("SCENARIO_DCF requires dcf assumptions")
        if self.method is ValuationMethod.REVERSE_DCF and self.reverse_dcf is None:
            raise ValueError("REVERSE_DCF requires reverse_dcf assumptions")
        if self.method is ValuationMethod.OBSERVED_MULTIPLES:
            if self.explicit_multiple is None or self.metric_value is None:
                raise ValueError("OBSERVED_MULTIPLES requires explicit_multiple and metric_value")
        return self
