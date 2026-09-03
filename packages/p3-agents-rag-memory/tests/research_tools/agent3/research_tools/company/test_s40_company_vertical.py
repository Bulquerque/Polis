from datetime import UTC, datetime
import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.handlers import build_guidance_valuation_bundle, build_profile_bundle, build_statement_bundle, build_analysis_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import ExtensionLineage
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.qualification import combine_company_tool_bundle
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.company_adapter import build_company_operations
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import CompositeResearchToolGateway
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.registry import OperationRegistry
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import RequestValidationStatus, ToolCallRequestRecord, ToolExecutionStatus, ValidatedToolCallRequestRecord
from ._fixtures import InMemoryCompanyPort

def request():
    raw=ToolCallRequestRecord(tool_call_request_id="req-company",cognition_transaction_id="tx-company",person_id="p1",tool_id="company.fundamentals.v1",operation_id="get_profile",arguments={"entity_id":"E1","research_mode":"QUICK_CHECK"},reason="test",expected_information_gain=0.5,requested_at=datetime(2024,4,1,tzinfo=UTC),as_of=datetime(2024,4,1,tzinfo=UTC),idempotency_key="idem-company")
    return ValidatedToolCallRequestRecord(request=raw,validation_status=RequestValidationStatus.ACCEPTED,provider_id="internal_research",entitlement_version="v1",arguments_schema={},result_schema={},read_only=True,point_in_time_safe=True)

@pytest.mark.asyncio
async def test_company_bundle_executes_through_s40_gateway():
    lineage=ExtensionLineage(lineage_id="l",producer_module_id="P3.S38.M06")
    bundle=combine_company_tool_bundle(bundles=(build_profile_bundle(lineage),build_statement_bundle(lineage),build_analysis_bundle(lineage),build_guidance_valuation_bundle(lineage)),lineage=lineage)
    operations=build_company_operations(tool_bundle=bundle,query_port=InMemoryCompanyPort())
    gateway=CompositeResearchToolGateway(registry=OperationRegistry(operations),snapshot_id="s1",execution_profile="TEST")
    result=await gateway.execute(request())
    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.canonical_payload["operation_id"] == "get_profile"
    assert result.canonical_payload["records"][0]["legal_name"] == "Old Co"
