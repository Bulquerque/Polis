from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.canonical_support import (
    request_model,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.unified_runner import (
    execute_unified_batch,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    RequestValidationStatus,
    ToolExecutionStatus,
)

from tests.research_tools.unified.test_cross_agent_runtime import _gateway, _validated_request


_DECISION = "2024-01-01T00:00:00Z"
_END = "2024-01-10T00:00:00Z"


def _case(tool_id: str, operation_id: str, arguments: Mapping[str, object]) -> tuple[str, str, dict[str, object]]:
    return tool_id, operation_id, dict(arguments)


AGENT_TOOL_CALLS = (
    _case("research.corpus.v1", "search", {"research_mode": "LOOKUP", "query": "debt refinancing", "entity_ids": ["E1"], "max_results": 5}),
    _case("research.corpus.v1", "get_document", {"research_mode": "LOOKUP", "document_id": "DOC1"}),
    _case("research.corpus.v1", "compare_versions", {"research_mode": "STANDARD", "document_ids": ["DOC1", "DOC2"]}),
    _case("research.corpus.v1", "find_counterevidence", {"research_mode": "STANDARD", "proposition": "Revenue growth is sustainable.", "entity_ids": ["E1"], "max_results": 5}),
    _case("research.corpus.v1", "build_timeline", {"research_mode": "LOOKUP", "subject_ids": ["E1"]}),
    _case("research.corpus.v1", "inspect_provenance", {"research_mode": "LOOKUP", "evidence_ids": ["ev1"]}),
    _case("market.observation.v1", "get_snapshot", {"research_mode": "OBSERVE", "instrument_ids": ["ACME3"]}),
    _case("market.observation.v1", "get_history", {"research_mode": "OBSERVE", "instrument_ids": ["ACME3"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("market.observation.v1", "get_liquidity", {"research_mode": "OBSERVE", "instrument_ids": ["ACME3"]}),
    _case("market.observation.v1", "get_corporate_actions", {"research_mode": "OBSERVE", "instrument_ids": ["ACME3"]}),
    _case("market.observation.v1", "compare_instruments", {"research_mode": "OBSERVE", "instrument_ids": ["ACME3", "ACME4"], "start_time": _DECISION, "end_time": _END}),
    _case("options.observation.v1", "get_contracts", {"research_mode": "CONTRACT_LOOKUP", "underlying_ids": ["ACME3"]}),
    _case("options.observation.v1", "get_chain_snapshot", {"research_mode": "CONTRACT_LOOKUP", "underlying_id": "ACME3"}),
    _case("options.observation.v1", "get_quote_history", {"research_mode": "CHAIN_DIAGNOSTIC", "contract_ids": ["ACME3-C100"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("options.observation.v1", "get_surface_diagnostics", {"research_mode": "SURFACE_ANALYSIS", "underlying_id": "ACME3"}),
    _case("macro.observation.v1", "search_series", {"research_mode": "LOOKUP", "query": "inflation"}),
    _case("macro.observation.v1", "get_observations", {"research_mode": "LOOKUP", "series_ids": ["CPI"], "start_time": _DECISION, "end_time": _END}),
    _case("macro.observation.v1", "get_release_snapshot", {"research_mode": "LOOKUP", "release_ids": ["CPI_RELEASE"]}),
    _case("macro.observation.v1", "compare_series", {"research_mode": "CONTEXT", "series_ids": ["CPI", "GDP"], "start_time": _DECISION, "end_time": _END}),
    _case("macro.observation.v1", "get_asset_context", {"research_mode": "LOOKUP", "instrument_ids": ["ACME3"]}),
    _case("company.fundamentals.v1", "get_profile", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "get_financial_statements", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "get_fundamental_snapshot", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "get_guidance", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "get_capital_allocation", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "get_peers", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]}),
    _case("company.fundamentals.v1", "calculate_valuation", {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"], "method": "MULTIPLES", "assumptions": {"explicit_multiple": 10.0, "metric_value": 100.0}, "currency": "USD"}),
    _case("quant.diagnostics.v1", "return_statistics", {"research_mode": "BASIC", "instrument_ids": ["ACME3"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("quant.diagnostics.v1", "realized_volatility", {"research_mode": "BASIC", "returns": [0.01, -0.02, 0.015, 0.005], "estimator": "standard_deviation", "annualization_factor": 252.0}),
    _case("quant.diagnostics.v1", "drawdown", {"research_mode": "BASIC", "instrument_ids": ["ACME3"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("quant.diagnostics.v1", "correlation", {"research_mode": "BASIC", "instrument_ids": ["ACME3", "ACME4"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("quant.diagnostics.v1", "entropy", {"research_mode": "BASIC", "instrument_ids": ["ACME3"], "start_time": _DECISION, "end_time": _END, "frequency": "1d"}),
    _case("quant.diagnostics.v1", "event_window", {"research_mode": "BASIC", "event_ids": ["EV1"], "instrument_ids": ["ACME3"], "pre_observations": 2, "post_observations": 2, "frequency": "1d"}),
    _case("quant.diagnostics.v1", "scenario_shock", {"research_mode": "BASIC", "exposures": {"ACME3": 1.0}, "shocks": {"ACME3": -0.1}, "relationships": {}}),
)


@pytest.mark.asyncio
async def test_agent_can_execute_every_declared_operation_through_gateway() -> None:
    gateway = _gateway()
    assert len(AGENT_TOOL_CALLS) == 34
    assert len({(tool_id, operation_id) for tool_id, operation_id, _ in AGENT_TOOL_CALLS}) == 34
    requests = []
    for tool_id, operation_id, arguments in AGENT_TOOL_CALLS:
        request = request_model(tool_id, operation_id).model_validate(arguments, strict=False)
        requests.append(_validated_request(tool_id, operation_id, request.model_dump(mode="json")))
    receipt = await execute_unified_batch(
        gateway,
        requests,
        run_id="unified-run-1",
        cycle_id="cycle-1",
        decision_time=datetime(2024, 1, 1, tzinfo=UTC),
        snapshot_id="snapshot-1",
    )
    assert receipt.status == "PASS"
    assert receipt.operation_count == 34
    assert receipt.succeeded_count == 34
    assert receipt.failed_count == 0
    assert receipt.family_counts == {
        "corpus": 6,
        "market": 5,
        "options": 4,
        "macro": 5,
        "company": 7,
        "quant": 7,
    }
    assert receipt.receipt_hash


@pytest.mark.asyncio
async def test_agent_gateway_rejects_non_accepted_requests_fail_closed() -> None:
    gateway = _gateway()
    tool_id, operation_id, arguments = AGENT_TOOL_CALLS[0]
    request = request_model(tool_id, operation_id).model_validate(arguments, strict=False)
    rejected = _validated_request(tool_id, operation_id, request.model_dump(mode="json")).model_copy(
        update={"validation_status": RequestValidationStatus.REJECTED_SCHEMA}
    )
    response = await gateway.execute(rejected)
    assert response.status is ToolExecutionStatus.REJECTED_AUTHORIZATION
    assert response.response_hash is None
    assert response.error is not None
    assert response.error.code == "P3RT-AUTH-REQUEST-NOT-ACCEPTED"


def test_agents_discover_only_callable_operations_from_the_dispatch_registry() -> None:
    gateway = _gateway()
    discovered = gateway.discover()
    assert len(discovered) == 34
    assert [(item.tool_id, item.operation_id) for item in discovered] == sorted(
        (item.tool_id, item.operation_id) for item in discovered
    )
    assert all(item.transport.value not in {"MCP_OPTIONAL", "HTTP_OPTIONAL"} for item in discovered)
    assert all(item.qualification_status.value != "BLOCKED_UPSTREAM" for item in discovered)


@pytest.mark.asyncio
async def test_alias_cannot_override_a_fixed_argument() -> None:
    gateway = _gateway()
    request = _validated_request(
        "quant.realized_volatility.v1",
        "calculate",
        {
            "research_mode": "LOOKUP",
            "returns": [0.01, -0.02, 0.015, 0.005],
            "estimator": "standard_deviation",
            "annualization_factor": 252.0,
        },
    )
    response = await gateway.execute(request)
    assert response.status is ToolExecutionStatus.FAILED_SCHEMA
    assert response.response_hash is None
    assert response.error is not None
    assert response.error.code == "P3RT-ALIAS-FIXED-ARGUMENT-CONFLICT"
