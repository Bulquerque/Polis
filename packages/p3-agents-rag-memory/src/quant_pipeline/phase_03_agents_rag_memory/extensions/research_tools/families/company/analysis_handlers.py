"""Deterministic fundamental snapshot and capital-allocation handlers."""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .calculations import safe_ratio
from .data_access import query_company_records, view_declared
from .models import CompanyCallContext, GetCapitalAllocationRequest, GetFundamentalSnapshotRequest, OutcomeStatus
from .outcomes import build_company_result
from .ports import PitResearchQueryPort


def _latest_values(records):
    values = {}
    for item in sorted(records, key=lambda row: str(row.get("period_end", row.get("available_at")))):
        concept = str(item.get("concept_id", ""))
        value = item.get("value")
        if concept and isinstance(value, (int, float)):
            values[concept] = float(value)
    return values


def _snapshot_metrics(values):
    revenue = values.get("revenue")
    operating_income = values.get("operating_income")
    net_income = values.get("net_income")
    operating_cash_flow = values.get("operating_cash_flow")
    debt = values.get("total_debt")
    cash = values.get("cash")
    ebitda = values.get("ebitda")
    result = {}
    ratios = {
        "operating_margin": safe_ratio(operating_income, revenue),
        "cash_conversion": safe_ratio(operating_cash_flow, net_income),
        "net_debt_to_ebitda": safe_ratio(
            None if debt is None or cash is None else debt - cash, ebitda
        ),
    }
    for key, value in ratios.items():
        if value is not None:
            result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class GetFundamentalSnapshotHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetFundamentalSnapshotRequest, context: CompanyCallContext):
        visible, rejected = await query_company_records(
            self.query_port, view_id=request.view_id, entity_id=request.entity_id,
            decision_time=context.decision_time, extra_filters={"periods": request.periods},
        )
        values = _latest_values(visible)
        metrics = _snapshot_metrics(values)
        empty_valid = not visible and view_declared(self.query_port, request.view_id)
        missing = tuple(sorted(set(request.formula_ids) - set(metrics)))
        return build_company_result(
            operation_id="get_fundamental_snapshot", requested_mode=request.research_mode,
            executed_mode=request.research_mode, method_id="company.fundamental.snapshot.v1",
            metrics=metrics, records=visible, records_requested=request.periods,
            records_rejected_future=rejected, missing_requirements=missing,
            outcome_status=(None if visible else (OutcomeStatus.EMPTY_VALID if empty_valid else OutcomeStatus.BLOCKED_UPSTREAM)),
            reason_codes=(
                ("P3RT-FINANCIAL-STATEMENTS-EMPTY-VALID",) if empty_valid
                else (("P3RT-UPSTREAM-FINANCIAL-STATEMENTS-MISSING",) if not visible else ())
            ),
        )


@dataclass(frozen=True, slots=True)
class GetCapitalAllocationHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetCapitalAllocationRequest, context: CompanyCallContext):
        statements, rejected_s = await query_company_records(
            self.query_port, view_id=request.statement_view_id, entity_id=request.entity_id,
            decision_time=context.decision_time, extra_filters={"periods": request.periods},
        )
        actions, rejected_a = await query_company_records(
            self.query_port, view_id=request.corporate_action_view_id, entity_id=request.entity_id,
            decision_time=context.decision_time, extra_filters={"periods": request.periods},
        )
        values = _latest_values(statements)
        metrics = {
            "capex": values.get("capital_expenditure", 0.0),
            "dividends": sum(float(x.get("amount", 0.0)) for x in actions if x.get("action_type") == "DIVIDEND"),
            "buybacks": sum(float(x.get("amount", 0.0)) for x in actions if x.get("action_type") == "BUYBACK"),
            "issuance": sum(float(x.get("amount", 0.0)) for x in actions if x.get("action_type") == "ISSUANCE"),
        }
        records = tuple(statements) + tuple(actions)
        empty_valid = not records and view_declared(self.query_port, request.statement_view_id) and view_declared(self.query_port, request.corporate_action_view_id)
        return build_company_result(
            operation_id="get_capital_allocation", requested_mode=request.research_mode,
            executed_mode=request.research_mode, method_id="company.capital.allocation.v1", metrics=metrics,
            records=records, records_requested=request.periods * 2,
            records_rejected_future=rejected_s + rejected_a,
            missing_requirements=(() if records or empty_valid else ("financial_statements", "corporate_actions")),
            outcome_status=(None if records else (OutcomeStatus.EMPTY_VALID if empty_valid else OutcomeStatus.BLOCKED_UPSTREAM)),
            reason_codes=(
                ("P3RT-CAPITAL-ALLOCATION-EMPTY-VALID",) if empty_valid
                else (("P3RT-UPSTREAM-CAPITAL-ALLOCATION-DATA-MISSING",) if not records else ())
            ),
        )
