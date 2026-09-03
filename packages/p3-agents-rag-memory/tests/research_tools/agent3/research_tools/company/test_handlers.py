from datetime import UTC, datetime
import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.handlers import CompanyHandlerFactory
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import (
    CompanyCallContext, GetFinancialStatementsRequest, GetProfileRequest, CalculateValuationRequest, DcfAssumptions, OutcomeStatus,
)
from ._fixtures import InMemoryCompanyPort

CTX=CompanyCallContext(request_id="r1",person_id="p1",decision_time=datetime(2024,4,1,tzinfo=UTC),snapshot_id="s1")

@pytest.mark.asyncio
async def test_profile_rejects_future_version():
    result=await CompanyHandlerFactory(InMemoryCompanyPort()).build()["get_profile"].execute(GetProfileRequest(entity_id="E1"),CTX)
    assert result.records[0]["legal_name"] == "Old Co"
    assert result.coverage.records_rejected_future == 1

@pytest.mark.asyncio
async def test_statement_before_restatement_returns_original_only_visible():
    result=await CompanyHandlerFactory(InMemoryCompanyPort()).build()["get_financial_statements"].execute(GetFinancialStatementsRequest(entity_id="E1",periods=3),CTX)
    ids={row["record_id"] for row in result.records}
    assert "rev-original" in ids and "rev-restated" not in ids
    assert result.coverage.records_rejected_future == 1

@pytest.mark.asyncio
async def test_valuation_is_scenario_not_recommendation():
    request=CalculateValuationRequest(entity_id="E1",dcf=DcfAssumptions(base_free_cash_flow=10.0,growth_rates=(0.03,)*3,discount_rate=0.1,terminal_growth_rate=0.02,shares_outstanding=2.0))
    result=await CompanyHandlerFactory(InMemoryCompanyPort()).build()["calculate_valuation"].execute(request,CTX)
    assert result.outcome_status is OutcomeStatus.PASS
    assert "scenario_value_per_share" in result.metrics
    assert "target_price" not in result.metrics
