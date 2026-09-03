"""Scenario-only valuation handlers with explicit assumptions."""
from __future__ import annotations

from dataclasses import dataclass

from .calculations import reverse_dcf, scenario_dcf
from .models import CalculateValuationRequest, CompanyCallContext, OutcomeStatus, ValuationMethod
from .outcomes import build_company_result
from .ports import PitResearchQueryPort


@dataclass(frozen=True, slots=True)
class CalculateValuationHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: CalculateValuationRequest, context: CompanyCallContext):
        del context
        if request.method is ValuationMethod.SCENARIO_DCF:
            assert request.dcf is not None
            metrics = scenario_dcf(request.dcf)
            method_id = "company.valuation.scenario_dcf.v1"
        elif request.method is ValuationMethod.REVERSE_DCF:
            assert request.reverse_dcf is not None
            metrics = reverse_dcf(request.reverse_dcf)
            method_id = "company.valuation.reverse_dcf.v1"
            if not bool(metrics["target_bracketed"]):
                return build_company_result(
                    operation_id="calculate_valuation",
                    requested_mode=request.research_mode,
                    executed_mode=request.research_mode,
                    method_id=method_id,
                    metrics=metrics,
                    records=(),
                    records_requested=1,
                    records_rejected_future=0,
                    missing_requirements=("reverse_dcf_growth_bounds_do_not_bracket_market_value",),
                    outcome_status=OutcomeStatus.DEGRADED,
                    reason_codes=("P3RT-METHOD-REVERSE-DCF-NOT-BRACKETED",),
                    diagnostics=("nearest_growth_bound_returned", "scenario_value_not_target_price"),
                    cost_units=2,
                )
        elif request.method is ValuationMethod.OBSERVED_MULTIPLES:
            assert request.explicit_multiple is not None and request.metric_value is not None
            metrics = {"scenario_enterprise_value": request.explicit_multiple * request.metric_value}
            method_id = "company.valuation.explicit_multiple.v1"
        else:
            return build_company_result(
                operation_id="calculate_valuation", requested_mode=request.research_mode,
                executed_mode=request.research_mode, method_id="company.valuation.unavailable.v1",
                metrics={}, records=(), records_requested=1, records_rejected_future=0,
                missing_requirements=("qualified_peer_or_history_view",),
                outcome_status=OutcomeStatus.BLOCKED_UPSTREAM,
                reason_codes=("P3RT-UPSTREAM-VALUATION-COMPARABLES-MISSING",),
            )
        return build_company_result(
            operation_id="calculate_valuation", requested_mode=request.research_mode,
            executed_mode=request.research_mode, method_id=method_id, metrics=metrics, records=(),
            records_requested=1, records_rejected_future=0, cost_units=2,
            diagnostics=("scenario_value_not_target_price", "no_investment_recommendation"),
        )
