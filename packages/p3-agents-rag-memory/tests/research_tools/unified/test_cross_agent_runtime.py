from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.contracts.execution import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.handlers import (
    build_analysis_bundle,
    build_guidance_valuation_bundle,
    build_profile_bundle,
    build_statement_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import (
    ExtensionLineage as CompanyLineage,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.qualification import (
    combine_company_tool_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.models import (
    CapabilityReadiness,
    CapabilityStatus,
    CorpusArtifactRef,
    CorpusIndexSnapshot,
    CorpusMode,
    CorpusRetrievalPolicy,
    HandlerBundleManifest as CorpusManifest,
    HandlerSpec as CorpusHandlerSpec,
    ModePolicy,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.models import (
    AssetMacroContextRegistrySnapshot,
    Frequency,
    HandlerBundleManifest as MacroManifest,
    HandlerSpec as MacroHandlerSpec,
    MacroSeriesDefinition,
    MacroSeriesReleaseCatalog,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.ports import (
    VisibleMacroRecordBatch,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.models import (
    HandlerBundleManifest as MarketManifest,
    HandlerSpec as MarketHandlerSpec,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.ports import (
    VisibleRecordBatch,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.handlers import (
    build_dependence_entropy_bundle,
    build_event_scenario_bundle,
    build_return_risk_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    ExtensionLineage as QuantLineage,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.qualification import (
    combine_quant_tool_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly_support import (
    registry,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.gateway import (
    CompositeResearchToolGateway,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.models import Chunk
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    RequestValidationStatus,
    ToolCallRequestRecord,
    ToolExecutionStatus,
    ValidatedToolCallRequestRecord,
)

ROOT = Path(__file__).resolve().parents[3]
DECISION = datetime(2024, 1, 10, tzinfo=UTC)


class CorpusRepository:
    def __init__(self) -> None:
        payload = "Debt refinancing risk declined after the filing."
        self._chunks = (
            Chunk(
                chunk_id="chunk-1",
                document_id="filing-1",
                source_id="sec",
                sequence_number=0,
                start_word=0,
                end_word=7,
                content=payload,
                content_hash=content_hash(payload),
                available_at=datetime(2024, 1, 5, tzinfo=UTC),
                source_quality=0.95,
                entities=("E1",),
                underlyings=("ACME3",),
                lineage_refs=("p2:document:1",),
                chunker_version="1.0.0",
            ),
        )

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    @property
    def keyword_index(self) -> Mapping[str, tuple[str, ...]]:
        return {"debt": ("chunk-1",), "refinancing": ("chunk-1",)}

    def chunks_for_document(self, document_id: str) -> tuple[Chunk, ...]:
        return tuple(item for item in self._chunks if item.document_id == document_id)

    def chunk(self, chunk_id: str) -> Chunk | None:
        return next((item for item in self._chunks if item.chunk_id == chunk_id), None)

    def document_metadata(self, document_id: str) -> Mapping[str, object]:
        return {"document_id": document_id, "document_type": "FILING", "available_at": "2024-01-05T00:00:00Z"}

    def supports_metadata_field(self, field_name: str) -> bool:
        return field_name in {"document_type", "available_at"}


class MarketPort:
    def query(self, view_name: str, *, decision_time: datetime, filters: Mapping[str, object] | None = None) -> VisibleRecordBatch:
        assert decision_time == DECISION
        rows: tuple[Mapping[str, object], ...] = ()
        if view_name == "clean_underlying_panel":
            instrument = str((filters or {}).get("underlying") or "ACME3")
            rows = ({
                "underlying": instrument,
                "date": "2024-01-09",
                "available_at": "2024-01-09T20:00:00Z",
                "open": 99.0,
                "high": 102.0,
                "low": 98.0,
                "close": 101.0,
                "volume": 1000.0,
                "source_id": "fixture-market",
                "lineage_id": "p2:market:1",
                "quality_flag": "PASS",
                "content_hash": "b" * 64,
            },)
        return VisibleRecordBatch(
            view_name=view_name,
            snapshot_id="snapshot-1",
            rows=rows,
            records_scanned=len(rows),
            records_rejected_future=0,
            records_rejected_missing_time=0,
            records_rejected_filter=0,
            input_hashes=("b" * 64,),
        )

    def available_fields(self, view_name: str) -> frozenset[str]:
        del view_name
        return frozenset({"underlying", "date", "available_at", "close"})

    def record_count(self, view_name: str) -> int:
        del view_name
        return 1


class MacroPort:
    def query(self, view_name: str, *, decision_time: datetime, filters: Mapping[str, object] | None = None) -> VisibleMacroRecordBatch:
        del filters
        assert decision_time == DECISION
        rows: tuple[Mapping[str, object], ...] = ()
        if view_name == "clean_macro_us_panel":
            rows = ({
                "series_id": "CPI",
                "date": "2023-12-01",
                "value": 3.2,
                "unit": "PERCENT",
                "frequency": "MONTHLY",
                "available_at": "2024-01-05T13:30:00Z",
                "published_at": "2024-01-05T13:30:00Z",
                "vintage_date": "2024-01-05",
                "revision_id": "original",
                "release_id": "CPI_RELEASE",
                "is_original_release": True,
                "source_id": "fixture-macro",
                "lineage_id": "p2:macro:1",
                "content_hash": "a" * 64,
            },)
        return VisibleMacroRecordBatch(
            view_name=view_name,
            snapshot_id="snapshot-1",
            rows=rows,
            records_scanned=len(rows),
            records_rejected_future=0,
            records_rejected_missing_time=0,
            records_rejected_filter=0,
            input_hashes=("a" * 64,),
        )

    def available_fields(self, view_name: str) -> frozenset[str]:
        del view_name
        return frozenset({"series_id", "date", "value", "available_at", "vintage_date"})

    def record_count(self, view_name: str) -> int:
        return 1 if view_name == "clean_macro_us_panel" else 0


class GenericPitPort:
    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, object],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, object]]:
        assert decision_time == DECISION
        if view_id == "company_profile":
            return ({
                "record_id": "company-1",
                "entity_id": str(filters.get("entity_id") or "E1"),
                "legal_name": "ACME Corp",
                "effective_from": "2020-01-01",
                "available_at": "2024-01-01T00:00:00Z",
                "source_id": "fixture-company",
                "artifact_id": "company-artifact",
                "source_quality": 0.95,
                "content_hash": "c" * 64,
            },)
        if view_id == "events":
            return ({
                "event_id": "EV1",
                "event_time": "2024-01-05T10:00:00Z",
                "available_at": "2024-01-05T12:00:00Z",
                "source_id": "fixture-event",
                "artifact_id": "event-artifact",
                "content_hash": "e" * 64,
            },)
        if view_id == "market_prices":
            instrument_id = str(filters.get("instrument_id") or "ACME3")
            closes = (98.0, 99.0, 100.0, 102.0, 101.0)
            return tuple({
                "instrument_id": instrument_id,
                "observation_time": f"2024-01-0{day}T16:00:00Z",
                "available_at": f"2024-01-0{day}T20:00:00Z",
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "source_id": "fixture-quant-market",
                "artifact_id": "quant-market-artifact",
                "content_hash": f"{day}" * 64,
            } for day, close in zip(range(3, 8), closes, strict=True))
        return ()


def _operation_records() -> list[dict[str, object]]:
    catalog = yaml.safe_load((ROOT / "config/research_tools/RESEARCH_TOOL_CATALOG.yaml").read_text())
    return [
        {"tool_id": tool["tool_id"], "provider_id": tool["default_provider_id"], **operation}
        for tool in catalog["tools"]
        for operation in tool["operations"]
    ]


def _manifest_inputs() -> tuple[dict[str, object], dict[str, object]]:
    records = _operation_records()
    aliases = yaml.safe_load((ROOT / "config/research_tools/COMPATIBILITY_ALIASES.yaml").read_text())

    corpus_specs = tuple(
        CorpusHandlerSpec(
            operation_id=item["operation_id"],
            handler_id=f"private.corpus.{item['operation_id']}",
            request_model="PrivateRequest",
            supported_modes=tuple(CorpusMode(mode) for mode in item["supported_mode_ids"]),
        )
        for item in records
        if item["tool_id"] == "research.corpus.v1"
    )
    corpus_base = {"bundle_id": "corpus-unified", "handlers": corpus_specs}
    corpus_manifest = CorpusManifest(content_hash=content_hash(corpus_base), **corpus_base)
    chunk_artifact = CorpusArtifactRef(
        artifact_type="fixture",
        uri="memory://corpus/chunks",
        content_hash="1" * 64,
        media_type="application/json",
        size_bytes=1,
        record_count=1,
        format_version="1",
    )
    keyword_artifact = CorpusArtifactRef(
        artifact_type="fixture",
        uri="memory://corpus/keywords",
        content_hash="5" * 64,
        media_type="application/json",
        size_bytes=1,
        record_count=1,
        format_version="1",
    )
    capabilities = tuple(
        CapabilityReadiness(
            capability_id=capability,
            status=CapabilityStatus.READY,
            qualification_status="QUALIFIED_LOCAL",
            snapshot_id="snapshot-1",
        )
        for capability in ("keyword_retrieval", "available_at_filtering")
    )
    snapshot_base = {
        "artifact_id": "corpus-snapshot",
        "run_id": "run-1",
        "snapshot_id": "snapshot-1",
        "as_of_time": DECISION,
        "retrieval_manifest_id": "retrieval-1",
        "retrieval_manifest_hash": "2" * 64,
        "rag_index_artifact_hash": "3" * 64,
        "chunk_schema_id": "chunks.v1",
        "chunk_count": 1,
        "chunk_catalog": chunk_artifact,
        "keyword_index": keyword_artifact,
        "vector_index": None,
        "capabilities": capabilities,
        "required_metadata_filters": ("available_at",),
        "configuration_hash": "4" * 64,
        "provider_fingerprints": {},
    }
    snapshot = CorpusIndexSnapshot(content_hash=content_hash(snapshot_base), **snapshot_base)
    mode_policies = tuple(
        ModePolicy(
            mode_id=mode,
            max_results=20,
            max_internal_subqueries=4,
            max_internal_work_units=40,
        )
        for mode in CorpusMode
    )
    policy_base = {"policy_id": "policy-1", "snapshot_id": "snapshot-1", "modes": mode_policies}
    policy = CorpusRetrievalPolicy(content_hash=content_hash(policy_base), **policy_base)

    family_manifests: dict[str, MarketManifest] = {}
    for tool_id in ("market.observation.v1", "options.observation.v1"):
        specs = tuple(
            MarketHandlerSpec(
                tool_id=tool_id,
                operation_id=item["operation_id"],
                handler_id=f"private.{tool_id}.{item['operation_id']}",
                request_model="PrivateRequest",
                supported_modes=tuple(item["supported_mode_ids"]),
            )
            for item in records
            if item["tool_id"] == tool_id
        )
        base = {
            "schema_id": "handler_bundle.s36.v1",
            "bundle_id": tool_id,
            "tool_id": tool_id,
            "handlers": specs,
        }
        family_manifests[tool_id] = MarketManifest(content_hash=content_hash(base), **base)

    macro_specs = tuple(
        MacroHandlerSpec(
            tool_id="macro.observation.v1",
            operation_id=item["operation_id"],
            handler_id=f"private.macro.{item['operation_id']}",
            request_model="PrivateRequest",
            supported_modes=tuple(item["supported_mode_ids"]),
            required_views=tuple(item["required_view_classes"]),
        )
        for item in records
        if item["tool_id"] == "macro.observation.v1"
    )
    macro_base = {
        "schema_id": "handler_bundle.s37.v1",
        "bundle_id": "macro-unified",
        "tool_id": "macro.observation.v1",
        "handlers": macro_specs,
    }
    macro_manifest = MacroManifest(content_hash=content_hash(macro_base), **macro_base)
    series = MacroSeriesDefinition(
        series_id="CPI",
        title="Consumer Price Index",
        region="US",
        country="US",
        family="INFLATION",
        unit="PERCENT",
        frequency=Frequency.MONTHLY,
        source_id="fixture-macro",
        release_id="CPI_RELEASE",
        vintage_support=True,
    )
    macro_catalog = MacroSeriesReleaseCatalog(
        snapshot_id="snapshot-1",
        records=(series,),
        content_hash=content_hash(series.model_dump(mode="json")),
    )
    macro_context = AssetMacroContextRegistrySnapshot(
        snapshot_id="snapshot-1",
        records=(),
        content_hash=content_hash({"records": []}),
    )

    company_lineage = CompanyLineage(lineage_id="company-lineage", producer_module_id="P3.S38.M06")
    company_bundle = combine_company_tool_bundle(
        bundles=(
            build_profile_bundle(company_lineage),
            build_statement_bundle(company_lineage),
            build_analysis_bundle(company_lineage),
            build_guidance_valuation_bundle(company_lineage),
        ),
        lineage=company_lineage,
    )
    quant_lineage = QuantLineage(lineage_id="quant-lineage", producer_module_id="P3.S39.M04")
    quant_bundle = combine_quant_tool_bundle(
        bundles=(
            build_return_risk_bundle(quant_lineage),
            build_dependence_entropy_bundle(quant_lineage),
            build_event_scenario_bundle(quant_lineage),
        ),
        lineage=quant_lineage,
    )

    inputs: dict[str, object] = {
        "canonical_tool_operation_registry": {"operations": records},
        "compatibility_alias_registry": aliases,
        "corpus_tool_handler_bundle": corpus_manifest.model_dump(mode="json"),
        "corpus_index_snapshot": snapshot.model_dump(mode="json"),
        "corpus_retrieval_policy": policy.model_dump(mode="json"),
        "market_tool_handler_bundle": family_manifests["market.observation.v1"].model_dump(mode="json"),
        "options_tool_handler_bundle": family_manifests["options.observation.v1"].model_dump(mode="json"),
        "macro_tool_handler_bundle": macro_manifest.model_dump(mode="json"),
        "macro_series_release_catalog": macro_catalog.model_dump(mode="json"),
        "macro_asset_context_config_snapshot": macro_context.model_dump(mode="json"),
        "company_tool_handler_bundle": company_bundle.model_dump(mode="json"),
        "quant_tool_handler_bundle": quant_bundle.model_dump(mode="json"),
    }
    services: dict[str, object] = {
        "corpus_repository": CorpusRepository(),
        "pit_market_query_port": MarketPort(),
        "pit_macro_query_port": MacroPort(),
        "company_pit_query_port": GenericPitPort(),
        "quant_pit_query_port": GenericPitPort(),
    }
    return inputs, services


def _validated_request(tool_id: str, operation_id: str, arguments: Mapping[str, object]) -> ValidatedToolCallRequestRecord:
    raw = ToolCallRequestRecord(
        tool_call_request_id=f"request-{tool_id}-{operation_id}",
        cognition_transaction_id="transaction-1",
        person_id="person-1",
        tool_id=tool_id,
        operation_id=operation_id,
        arguments=dict(arguments),
        reason="cross-agent integration test",
        expected_information_gain=0.5,
        requested_at=DECISION,
        as_of=DECISION,
        idempotency_key=f"idem-{tool_id}-{operation_id}",
    )
    return ValidatedToolCallRequestRecord(
        request=raw,
        validation_status=RequestValidationStatus.ACCEPTED,
        provider_id="internal_research",
        entitlement_version="unified-v1",
        arguments_schema={},
        result_schema={},
        read_only=True,
        point_in_time_safe=True,
    )


def _gateway() -> CompositeResearchToolGateway:
    inputs, services = _manifest_inputs()
    operation_registry = registry(ModuleExecutionContext(services=services), inputs)
    assert len(operation_registry.operations) == 34
    assert len(operation_registry.aliases) == 2
    canonical_handlers = {
        item["handler_id"] for item in inputs["canonical_tool_operation_registry"]["operations"]
    }
    assert {item.descriptor.handler_id for item in operation_registry.operations} == canonical_handlers
    return CompositeResearchToolGateway(
        registry=operation_registry,
        snapshot_id="snapshot-1",
        execution_profile="BACKTEST",
        deterministic_seed=7,
    )


def test_all_six_families_assemble_into_one_registry() -> None:
    gateway = _gateway()
    assert len(gateway._registry.operations) == 34
    assert {item.descriptor.tool_id for item in gateway._registry.operations} == {
        "research.corpus.v1",
        "market.observation.v1",
        "options.observation.v1",
        "macro.observation.v1",
        "company.fundamentals.v1",
        "quant.diagnostics.v1",
    }


@pytest.mark.asyncio
async def test_corpus_market_macro_and_company_execute_through_unified_gateway() -> None:
    gateway = _gateway()
    calls = (
        _validated_request(
            "research.corpus.v1",
            "search",
            {"research_mode": "LOOKUP", "query": "debt refinancing", "entity_ids": ["E1"], "max_results": 5},
        ),
        _validated_request(
            "market.observation.v1",
            "get_snapshot",
            {"research_mode": "OBSERVE", "instrument_ids": ["ACME3"]},
        ),
        _validated_request(
            "macro.observation.v1",
            "get_observations",
            {
                "research_mode": "LOOKUP",
                "series_ids": ["CPI"],
                "start_time": "2023-12-01T00:00:00Z",
                "end_time": "2024-01-10T00:00:00Z",
                "vintage_policy": "KNOWN_AT_DECISION_TIME",
            },
        ),
        _validated_request(
            "company.fundamentals.v1",
            "get_profile",
            {"research_mode": "QUICK_CHECK", "entity_ids": ["E1"]},
        ),
    )
    results = [await gateway.execute(call) for call in calls]
    assert all(result.status is ToolExecutionStatus.SUCCEEDED for result in results)
    assert all(result.response_hash for result in results)
    assert results[0].canonical_payload["total_matches"] == 1
    assert results[1].canonical_payload["instrument_count"] == 1
    assert results[2].canonical_payload["series_count"] == 1
    assert results[3].canonical_payload["entity_count"] == 1


@pytest.mark.asyncio
async def test_legacy_quant_alias_resolves_without_second_handler() -> None:
    gateway = _gateway()
    request = _validated_request(
        "quant.realized_volatility.v1",
        "calculate",
        {
            "returns": [0.01, -0.02, 0.015, 0.005],
            "estimator": "standard_deviation",
            "annualization_factor": 252.0,
        },
    )
    result = await gateway.execute(request)
    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.canonical_payload["realized_volatility"] > 0.0
    assert result.canonical_payload["estimator"] == "standard_deviation"
