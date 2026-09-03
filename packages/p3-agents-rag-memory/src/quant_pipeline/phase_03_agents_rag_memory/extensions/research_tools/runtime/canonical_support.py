"""Canonical cross-agent adapter helpers.

This module is the anti-corruption layer between the Agent 1 public contracts and
Agent 2/3 family implementations. Public tool IDs, operation IDs, handler IDs,
schema references and result models always come from the Agent 1 contract pack.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash, utc
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts import operation_models as canonical

from .gateway_support import GatewayInvocationContext
from .models import OperationDescriptor, QualificationStatus, TransportKind
from .registry import ExecutableOperation

_CANONICAL_REQUEST_MODELS: dict[tuple[str, str], type[BaseModel]] = {
    ("research.corpus.v1", "search"): canonical.CorpusSearchRequest,
    ("research.corpus.v1", "get_document"): canonical.GetDocumentRequest,
    ("research.corpus.v1", "compare_versions"): canonical.CompareVersionsRequest,
    ("research.corpus.v1", "find_counterevidence"): canonical.FindCounterevidenceRequest,
    ("research.corpus.v1", "build_timeline"): canonical.BuildTimelineRequest,
    ("research.corpus.v1", "inspect_provenance"): canonical.InspectProvenanceRequest,
    ("market.observation.v1", "get_snapshot"): canonical.MarketSnapshotRequest,
    ("market.observation.v1", "get_history"): canonical.MarketHistoryRequest,
    ("market.observation.v1", "get_liquidity"): canonical.MarketLiquidityRequest,
    ("market.observation.v1", "get_corporate_actions"): canonical.CorporateActionsRequest,
    ("market.observation.v1", "compare_instruments"): canonical.CompareInstrumentsRequest,
    ("options.observation.v1", "get_contracts"): canonical.GetOptionContractsRequest,
    ("options.observation.v1", "get_chain_snapshot"): canonical.GetOptionChainSnapshotRequest,
    ("options.observation.v1", "get_quote_history"): canonical.GetOptionQuoteHistoryRequest,
    ("options.observation.v1", "get_surface_diagnostics"): canonical.OptionSurfaceDiagnosticsRequest,
    ("macro.observation.v1", "search_series"): canonical.SearchMacroSeriesRequest,
    ("macro.observation.v1", "get_observations"): canonical.GetMacroObservationsRequest,
    ("macro.observation.v1", "get_release_snapshot"): canonical.GetMacroReleaseSnapshotRequest,
    ("macro.observation.v1", "compare_series"): canonical.CompareMacroSeriesRequest,
    ("macro.observation.v1", "get_asset_context"): canonical.GetAssetMacroContextRequest,
    ("company.fundamentals.v1", "get_profile"): canonical.GetCompanyProfileRequest,
    ("company.fundamentals.v1", "get_financial_statements"): canonical.GetFinancialStatementsRequest,
    ("company.fundamentals.v1", "get_fundamental_snapshot"): canonical.GetFundamentalSnapshotRequest,
    ("company.fundamentals.v1", "get_guidance"): canonical.GetGuidanceRequest,
    ("company.fundamentals.v1", "get_capital_allocation"): canonical.GetCapitalAllocationRequest,
    ("company.fundamentals.v1", "get_peers"): canonical.GetPeersRequest,
    ("company.fundamentals.v1", "calculate_valuation"): canonical.CalculateValuationRequest,
    ("quant.diagnostics.v1", "return_statistics"): canonical.ReturnStatisticsRequest,
    ("quant.diagnostics.v1", "realized_volatility"): canonical.RealizedVolatilityRequest,
    ("quant.diagnostics.v1", "drawdown"): canonical.DrawdownRequest,
    ("quant.diagnostics.v1", "correlation"): canonical.CorrelationRequest,
    ("quant.diagnostics.v1", "entropy"): canonical.EntropyRequest,
    ("quant.diagnostics.v1", "event_window"): canonical.EventWindowRequest,
    ("quant.diagnostics.v1", "scenario_shock"): canonical.ScenarioShockRequest,
}

_CANONICAL_RESULT_MODELS: dict[tuple[str, str], type[BaseModel]] = {
    ("research.corpus.v1", "search"): canonical.CorpusSearchResult,
    ("research.corpus.v1", "get_document"): canonical.GetDocumentResult,
    ("research.corpus.v1", "compare_versions"): canonical.CompareVersionsResult,
    ("research.corpus.v1", "find_counterevidence"): canonical.FindCounterevidenceResult,
    ("research.corpus.v1", "build_timeline"): canonical.BuildTimelineResult,
    ("research.corpus.v1", "inspect_provenance"): canonical.InspectProvenanceResult,
    ("market.observation.v1", "get_snapshot"): canonical.MarketSnapshotResult,
    ("market.observation.v1", "get_history"): canonical.MarketHistoryResult,
    ("market.observation.v1", "get_liquidity"): canonical.MarketLiquidityResult,
    ("market.observation.v1", "get_corporate_actions"): canonical.CorporateActionsResult,
    ("market.observation.v1", "compare_instruments"): canonical.CompareInstrumentsResult,
    ("options.observation.v1", "get_contracts"): canonical.GetOptionContractsResult,
    ("options.observation.v1", "get_chain_snapshot"): canonical.GetOptionChainSnapshotResult,
    ("options.observation.v1", "get_quote_history"): canonical.GetOptionQuoteHistoryResult,
    ("options.observation.v1", "get_surface_diagnostics"): canonical.OptionSurfaceDiagnosticsResult,
    ("macro.observation.v1", "search_series"): canonical.SearchMacroSeriesResult,
    ("macro.observation.v1", "get_observations"): canonical.GetMacroObservationsResult,
    ("macro.observation.v1", "get_release_snapshot"): canonical.GetMacroReleaseSnapshotResult,
    ("macro.observation.v1", "compare_series"): canonical.CompareMacroSeriesResult,
    ("macro.observation.v1", "get_asset_context"): canonical.GetAssetMacroContextResult,
    ("company.fundamentals.v1", "get_profile"): canonical.GetCompanyProfileResult,
    ("company.fundamentals.v1", "get_financial_statements"): canonical.GetFinancialStatementsResult,
    ("company.fundamentals.v1", "get_fundamental_snapshot"): canonical.GetFundamentalSnapshotResult,
    ("company.fundamentals.v1", "get_guidance"): canonical.GetGuidanceResult,
    ("company.fundamentals.v1", "get_capital_allocation"): canonical.GetCapitalAllocationResult,
    ("company.fundamentals.v1", "get_peers"): canonical.GetPeersResult,
    ("company.fundamentals.v1", "calculate_valuation"): canonical.CalculateValuationResult,
    ("quant.diagnostics.v1", "return_statistics"): canonical.ReturnStatisticsResult,
    ("quant.diagnostics.v1", "realized_volatility"): canonical.RealizedVolatilityResult,
    ("quant.diagnostics.v1", "drawdown"): canonical.DrawdownResult,
    ("quant.diagnostics.v1", "correlation"): canonical.CorrelationResult,
    ("quant.diagnostics.v1", "entropy"): canonical.EntropyResult,
    ("quant.diagnostics.v1", "event_window"): canonical.EventWindowResult,
    ("quant.diagnostics.v1", "scenario_shock"): canonical.ScenarioShockResult,
}


def request_model(tool_id: str, operation_id: str) -> type[BaseModel]:
    return _CANONICAL_REQUEST_MODELS[(tool_id, operation_id)]


def result_model(tool_id: str, operation_id: str) -> type[BaseModel]:
    return _CANONICAL_RESULT_MODELS[(tool_id, operation_id)]


def canonical_operation_records(inputs: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = inputs.get("canonical_tool_operation_registry", inputs.get("tool_operation_registry", ()))
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json")
    if isinstance(raw, Mapping):
        raw = raw.get("operations", raw.get("records", ()))
    result: list[Mapping[str, Any]] = []
    for item in raw if isinstance(raw, (list, tuple)) else ():
        if isinstance(item, BaseModel):
            item = item.model_dump(mode="json")
        if isinstance(item, Mapping):
            result.append(item)
    return tuple(result)


def canonical_operation_record(
    inputs: Mapping[str, Any], tool_id: str, operation_id: str
) -> Mapping[str, Any] | None:
    for item in canonical_operation_records(inputs):
        if item.get("tool_id") == tool_id and item.get("operation_id") == operation_id:
            return item
    return None


def descriptor(
    *,
    inputs: Mapping[str, Any],
    tool_id: str,
    operation_id: str,
    bundle_id: str,
    qualification_status: QualificationStatus,
    fallback_binding: object | None = None,
) -> OperationDescriptor:
    record = canonical_operation_record(inputs, tool_id, operation_id)
    if record is None:
        if fallback_binding is None:
            raise ValueError(f"canonical operation missing: {tool_id}/{operation_id}")
        record = _binding_record(fallback_binding, tool_id, operation_id)
    transport = _transport(record.get("default_transport", record.get("transport", "COMPOSITE_INTERNAL")))
    supported = record.get("supported_mode_ids", record.get("supported_modes", ()))
    required = record.get("required_view_classes", record.get("required_view_ids", ()))
    return OperationDescriptor(
        tool_id=tool_id,
        operation_id=operation_id,
        handler_id=str(record.get("handler_id") or f"internal.{tool_id}.{operation_id}"),
        handler_version=str(record.get("operation_version") or record.get("handler_version") or "1.0.0"),
        provider_id=str(record.get("provider_id") or "internal_research"),
        transport=transport,
        request_schema_ref=str(record.get("request_schema_ref") or f"canonical://{tool_id}/{operation_id}/request"),
        result_schema_ref=str(record.get("result_schema_ref") or f"canonical://{tool_id}/{operation_id}/result"),
        supported_modes=tuple(str(getattr(mode, "value", mode)) for mode in supported),
        required_view_ids=tuple(str(item) for item in required),
        qualification_status=qualification_status,
        deterministic_or_seeded=bool(record.get("deterministic_or_seeded", True)),
        source_bundle_id=bundle_id,
    )


def _binding_record(binding: object, tool_id: str, operation_id: str) -> dict[str, Any]:
    if isinstance(binding, BaseModel):
        raw = binding.model_dump(mode="json")
    elif isinstance(binding, Mapping):
        raw = dict(binding)
    else:
        raw = {name: getattr(binding, name) for name in dir(binding) if not name.startswith("_")}
    raw.setdefault("tool_id", tool_id)
    raw.setdefault("operation_id", operation_id)
    return raw


def _transport(value: object) -> TransportKind:
    text = str(getattr(value, "value", value))
    aliases = {"MCP": "MCP_OPTIONAL", "HTTP": "HTTP_OPTIONAL"}
    return TransportKind(aliases.get(text, text))


def canonical_context(invocation: GatewayInvocationContext, context_model: type[BaseModel]) -> BaseModel:
    fields = context_model.model_fields
    values: dict[str, object] = {
        "request_id": invocation.request_id,
        "person_id": invocation.person_id,
        "decision_time": invocation.decision_time,
        "snapshot_id": invocation.snapshot_id,
        "deterministic_seed": invocation.deterministic_seed,
        "run_id": invocation.run_id,
        "cycle_id": invocation.cycle_id,
        "cognition_transaction_id": invocation.cognition_transaction_id,
    }
    return context_model(**{key: value for key, value in values.items() if key in fields})


def adapt_result(
    *,
    tool_id: str,
    operation_id: str,
    request: BaseModel,
    envelopes: Iterable[BaseModel | Mapping[str, Any]],
) -> BaseModel:
    dumps = [_dump(item) for item in envelopes]
    records_raw: list[Mapping[str, Any]] = []
    evidence_raw: list[Mapping[str, Any]] = []
    warnings: set[str] = set()
    truncated = False
    for item in dumps:
        records_raw.extend(row for row in item.get("records", ()) if isinstance(row, Mapping))
        evidence_raw.extend(row for row in item.get("evidence_refs", ()) if isinstance(row, Mapping))
        coverage = item.get("coverage", {})
        if isinstance(coverage, Mapping):
            truncated = truncated or bool(coverage.get("truncated", False))
        execution = item.get("execution", {})
        if isinstance(execution, Mapping):
            warnings.update(str(value) for value in execution.get("warnings", ()) if value)
        warnings.update(str(value) for value in item.get("warnings", ()) if value)
        if item.get("downgrade_reason"):
            warnings.add(str(item["downgrade_reason"]))
        if item.get("outcome_status") in {"DEGRADED", "BLOCKED_UPSTREAM"}:
            warnings.add(f"OUTCOME_{item['outcome_status']}")
    evidence = _canonical_evidence(records_raw, evidence_raw, dumps)
    kwargs: dict[str, Any] = {
        "records": evidence,
        "truncated": truncated,
        "warnings": tuple(sorted(warnings)),
    }
    kwargs.update(_operation_result_fields(tool_id, operation_id, request, records_raw, dumps))
    return result_model(tool_id, operation_id)(**kwargs)


def _dump(item: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, BaseModel):
        return item.model_dump(mode="json")
    return dict(item)


def _canonical_evidence(
    records: list[Mapping[str, Any]],
    evidence: list[Mapping[str, Any]],
    envelopes: list[Mapping[str, Any]],
) -> tuple[canonical.EvidenceRecord, ...]:
    fallback_available = _fallback_available_at(envelopes)
    fallback_source = str(evidence[0].get("source_id", "internal_research")) if evidence else "internal_research"
    result: list[canonical.EvidenceRecord] = []
    for index, row in enumerate(records):
        ev = evidence[index] if index < len(evidence) else {}
        available = row.get("available_at", ev.get("available_at", fallback_available))
        if available is None:
            available = fallback_available
        elif not isinstance(available, datetime):
            available = _datetime(available)
        source_id = str(row.get("source_id") or ev.get("source_id") or fallback_source)
        subject_id = _first(row, "subject_id", "entity_id", "instrument_id", "underlying", "asset_id", "series_id", "document_id")
        record_id = str(
            _first(row, "record_id", "chunk_id", "document_id", "event_id", "evidence_id", "content_hash")
            or content_hash(row)[:32]
        )
        result.append(
            canonical.EvidenceRecord(
                record_id=record_id,
                subject_id=str(subject_id) if subject_id is not None else None,
                source_id=source_id,
                available_at=available,
                values=dict(row),
            )
        )
    return tuple(result)


def _fallback_available_at(envelopes: list[Mapping[str, Any]]) -> datetime:
    candidates: list[datetime] = []
    for item in envelopes:
        pit = item.get("pit_proof", {})
        if isinstance(pit, Mapping):
            for key in ("latest_available_at", "decision_time"):
                value = pit.get(key)
                if value:
                    candidates.append(_datetime(value))
    return max(candidates) if candidates else datetime(1970, 1, 1, tzinfo=UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return utc(value)
    return utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _first(row: Mapping[str, Any], *keys: str) -> object | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _operation_result_fields(
    tool_id: str,
    operation_id: str,
    request: BaseModel,
    records: list[Mapping[str, Any]],
    envelopes: list[Mapping[str, Any]],
) -> dict[str, Any]:
    count = len(records)
    req = request.model_dump(mode="python")
    key = (tool_id, operation_id)
    if key == ("research.corpus.v1", "search"):
        return {"total_matches": count, "query_variants": ()}
    if key == ("research.corpus.v1", "get_document"):
        doc_hash = str(_first(records[0], "document_hash", "content_hash") if records else content_hash(req))
        return {"document_id": req["document_id"], "document_hash": doc_hash}
    if key == ("research.corpus.v1", "compare_versions"):
        changed = tuple(str(x) for row in records for x in row.get("changed_paths", ()))
        return {"version_order": tuple(req["document_ids"]), "changed_paths": tuple(sorted(set(changed)))}
    if key == ("research.corpus.v1", "find_counterevidence"):
        return {"proposition_hash": content_hash(req["proposition"]), "counterevidence_count": count}
    if key == ("research.corpus.v1", "build_timeline"):
        return {"event_count": count}
    if key == ("research.corpus.v1", "inspect_provenance"):
        return {"chain_count": count}
    if key == ("market.observation.v1", "get_snapshot"):
        return {"instrument_count": len(set(req["instrument_ids"]))}
    if key == ("market.observation.v1", "get_history"):
        return {"frequency": req["frequency"], "instrument_count": len(set(req["instrument_ids"]))}
    if key == ("market.observation.v1", "get_liquidity"):
        return {"metrics_computed": tuple(req["metrics"])}
    if key == ("market.observation.v1", "get_corporate_actions"):
        return {"action_count": count}
    if key == ("market.observation.v1", "compare_instruments"):
        return {"metrics_computed": tuple(req["metrics"])}
    if key[0] == "options.observation.v1" and operation_id != "get_surface_diagnostics":
        return {"contract_count": count}
    if key == ("options.observation.v1", "get_surface_diagnostics"):
        scores = [float(item.get("coverage", {}).get("score", 0.0)) for item in envelopes if isinstance(item.get("coverage"), Mapping)]
        return {"diagnostics_computed": tuple(req["diagnostics"]), "coverage_score": min(scores) if scores else 0.0}
    if key == ("macro.observation.v1", "search_series"):
        return {"series_count": count}
    if key == ("macro.observation.v1", "get_observations"):
        return {"series_count": len(set(req["series_ids"])), "vintage_policy": req["vintage_policy"]}
    if key == ("macro.observation.v1", "get_release_snapshot"):
        return {"release_count": count}
    if key == ("macro.observation.v1", "compare_series"):
        return {"series_count": len(set(req["series_ids"]))}
    if key == ("macro.observation.v1", "get_asset_context"):
        return {"factor_count": count}
    if key == ("company.fundamentals.v1", "get_profile"):
        return {"entity_count": len(set(req["entity_ids"]))}
    if key == ("company.fundamentals.v1", "get_financial_statements"):
        return {"statement_count": count}
    if key == ("company.fundamentals.v1", "get_fundamental_snapshot"):
        return {"metrics_computed": tuple(req["metrics"])}
    if key == ("company.fundamentals.v1", "get_guidance"):
        return {"guidance_count": count}
    if key == ("company.fundamentals.v1", "get_capital_allocation"):
        return {"event_count": count}
    if key == ("company.fundamentals.v1", "get_peers"):
        return {"peer_count": count}
    if key == ("company.fundamentals.v1", "calculate_valuation"):
        return {"method": req["method"], "assumptions_echo": req["assumptions"]}
    if key == ("quant.diagnostics.v1", "return_statistics"):
        return {"metrics_computed": tuple(req["metrics"])}
    if key == ("quant.diagnostics.v1", "realized_volatility"):
        value = _numeric(records, "realized_volatility", "volatility", default=0.0)
        return {"realized_volatility": max(0.0, value), "estimator": req["estimator"]}
    if key == ("quant.diagnostics.v1", "drawdown"):
        return {"maximum_drawdown": min(0.0, _numeric(records, "maximum_drawdown", "max_drawdown", default=0.0))}
    if key == ("quant.diagnostics.v1", "correlation"):
        return {"method": req["method"]}
    if key == ("quant.diagnostics.v1", "entropy"):
        return {"method": req["method"], "discretization_version": "1.0.0"}
    if key == ("quant.diagnostics.v1", "event_window"):
        return {"event_count": len(set(req["event_ids"]))}
    if key == ("quant.diagnostics.v1", "scenario_shock"):
        values = {str(k): float(v) for row in records for k, v in row.items() if isinstance(v, (int, float))}
        return {"scenario_values": values}
    raise KeyError(f"unsupported canonical result mapping: {tool_id}/{operation_id}")


def _numeric(records: list[Mapping[str, Any]], *keys: str, default: float) -> float:
    for row in records:
        for key in keys:
            value = row.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return default


def operation(
    *,
    inputs: Mapping[str, Any],
    tool_id: str,
    operation_id: str,
    bundle_id: str,
    qualification_status: QualificationStatus,
    handler: Any,
    context_factory: Any,
    fallback_binding: object | None = None,
) -> ExecutableOperation:
    return ExecutableOperation(
        descriptor=descriptor(
            inputs=inputs,
            tool_id=tool_id,
            operation_id=operation_id,
            bundle_id=bundle_id,
            qualification_status=qualification_status,
            fallback_binding=fallback_binding,
        ),
        request_model=request_model(tool_id, operation_id),
        result_model=result_model(tool_id, operation_id),
        handler=handler,
        context_factory=context_factory,
    )
