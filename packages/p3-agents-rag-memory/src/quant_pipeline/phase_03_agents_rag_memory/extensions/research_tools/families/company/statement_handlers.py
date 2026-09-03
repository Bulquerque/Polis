"""As-reported statement retrieval with explicit version preservation."""
from __future__ import annotations

from dataclasses import dataclass

from .data_access import query_company_records, view_declared
from .models import CompanyCallContext, GetFinancialStatementsRequest, OutcomeStatus
from .outcomes import build_company_result
from .ports import PitResearchQueryPort


def _statement_key(item):
    return (
        str(item.get("period_end", "")), str(item.get("filing_id", "")),
        str(item.get("filing_version", "")), str(item.get("concept_id", "")),
    )


@dataclass(frozen=True, slots=True)
class GetFinancialStatementsHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetFinancialStatementsRequest, context: CompanyCallContext):
        visible, rejected = await query_company_records(
            self.query_port, view_id=request.view_id, entity_id=request.entity_id,
            decision_time=context.decision_time,
            extra_filters={"statement_types": list(request.statement_types), "periods": request.periods},
        )
        filtered = tuple(
            item for item in visible
            if str(item.get("statement_type", "")) in set(request.statement_types)
        )
        if not request.include_restated_versions:
            latest = {}
            for item in sorted(filtered, key=_statement_key):
                key = (item.get("period_end"), item.get("statement_type"), item.get("concept_id"))
                latest[key] = item
            filtered = tuple(latest[key] for key in sorted(latest, key=str))
        else:
            filtered = tuple(sorted(filtered, key=_statement_key))
        empty_valid = not filtered and view_declared(self.query_port, request.view_id)
        return build_company_result(
            operation_id="get_financial_statements", requested_mode=request.research_mode,
            executed_mode=request.research_mode, method_id="company.statements.as_reported.v1",
            metrics={"facts_visible": len(filtered), "versions_preserved": request.include_restated_versions},
            records=filtered, records_requested=request.periods * len(request.statement_types),
            records_rejected_future=rejected,
            missing_requirements=(() if filtered or empty_valid else ("financial_statements",)),
            outcome_status=(None if filtered else (OutcomeStatus.EMPTY_VALID if empty_valid else OutcomeStatus.BLOCKED_UPSTREAM)),
            reason_codes=(
                ("P3RT-FINANCIAL-STATEMENTS-EMPTY-VALID",) if empty_valid
                else (() if filtered else ("P3RT-UPSTREAM-FINANCIAL-STATEMENTS-MISSING",))
            ),
        )
