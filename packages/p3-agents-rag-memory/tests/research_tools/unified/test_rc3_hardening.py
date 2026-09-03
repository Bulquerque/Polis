from __future__ import annotations

import ast
import asyncio
import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.calculations import reverse_dcf
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import ReverseDcfAssumptions
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.index_contracts import (
    CapabilityReadiness,
    CorpusArtifactRef,
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
    validate_snapshot_readiness_pair,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.corpus.types import (
    CapabilityStatus,
    QualificationStatus as CorpusQualificationStatus,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.catalog_contracts import (
    MacroSeriesReleaseCatalog,
    MacroViewReadinessReport,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.result_contracts import MacroSeriesDefinition
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.types import Frequency, ViewReadinessStatus
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.view_binding import MarketViewBindingBuilder
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.options.surface import build_surface_summary
from quant_pipeline.phase_03_agents_rag_memory.orchestration.module_contracts import validate_declared_module_metadata
from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import EXECUTABLE_MODULE_REGISTRY

ROOT = Path(__file__).resolve().parents[3]
EXTENSION = tuple(
    item for item in EXECUTABLE_MODULE_REGISTRY
    if ".extensions.research_tools.modules." in item.implementation_path
)
REQUIRED_CONTRACT_FIELDS = {
    "module_id", "module_name", "phase", "subphase", "status", "function", "inputs", "outputs",
    "validations", "invariants", "non_responsibilities", "fail_fast_conditions", "forbidden_fields",
    "allowed_connections", "tests_required", "definition_of_done", "observability_requirements",
    "debugging_contract", "change_control", "review_checklist",
}


def test_all_47_extension_contracts_are_complete_and_metadata_aligned() -> None:
    assert len(EXTENSION) == 47
    for registration in EXTENSION:
        module = importlib.import_module(registration.implementation_path)
        validate_declared_module_metadata(registration.module_id, module)
        contract = yaml.safe_load((ROOT / module.CONTRACT).read_text(encoding="utf-8"))
        assert not (REQUIRED_CONTRACT_FIELDS - set(contract)), registration.module_id
        assert set(contract.get("optional_inputs", ())) == set(getattr(module, "OPTIONAL_INPUTS", ()))


def test_wrappers_do_not_read_direct_undeclared_input_keys() -> None:
    for registration in EXTENSION:
        module = importlib.import_module(registration.implementation_path)
        path = ROOT / "src" / Path(*registration.implementation_path.split("."))
        path = path.with_suffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        read_keys: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "inputs":
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    read_keys.add(node.slice.value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "inputs" and node.func.attr == "get":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        read_keys.add(node.args[0].value)
        declared = set(module.REQUIRED_INPUTS) | set(getattr(module, "OPTIONAL_INPUTS", ()))
        assert read_keys <= declared, (registration.module_id, sorted(read_keys - declared))


def _corpus_snapshot() -> CorpusIndexSnapshot:
    chunk = CorpusArtifactRef(
        artifact_type="fixture", uri="memory://chunks", content_hash="1" * 64,
        media_type="application/json", size_bytes=1, record_count=1, format_version="1",
    )
    keyword = CorpusArtifactRef(
        artifact_type="fixture", uri="memory://keyword", content_hash="2" * 64,
        media_type="application/json", size_bytes=1, record_count=1, format_version="1",
    )
    capabilities = tuple(
        CapabilityReadiness(
            capability_id=capability_id, status=CapabilityStatus.READY,
            qualification_status="QUALIFIED_LOCAL", snapshot_id="snapshot-1",
        )
        for capability_id in ("keyword_retrieval", "available_at_filtering")
    )
    base = {
        "artifact_id": "corpus-1", "run_id": "run-1", "snapshot_id": "snapshot-1",
        "as_of_time": datetime(2024, 1, 1, tzinfo=UTC), "retrieval_manifest_id": "retrieval-1",
        "retrieval_manifest_hash": "3" * 64, "rag_index_artifact_hash": "4" * 64,
        "chunk_schema_id": "chunks.v1", "chunk_count": 1, "chunk_catalog": chunk,
        "keyword_index": keyword, "capabilities": capabilities,
        "required_metadata_filters": ("available_at",), "configuration_hash": "5" * 64,
        "provider_fingerprints": {},
    }
    return CorpusIndexSnapshot(content_hash=content_hash(base), **base)


def test_corpus_snapshot_and_readiness_must_match_exactly() -> None:
    snapshot = _corpus_snapshot()
    base = {
        "snapshot_id": "snapshot-1", "status": CorpusQualificationStatus.QUALIFIED_LOCAL,
        "lexical_ready": True, "semantic_ready": False, "reranker_ready": False,
        "point_in_time_filter_ready": True, "chunk_count": 1,
    }
    readiness = CorpusIndexReadinessReport(content_hash=content_hash(base), **base)
    validate_snapshot_readiness_pair(snapshot, readiness)
    bad = readiness.model_copy(update={"chunk_count": 2})
    with pytest.raises(ValueError, match="chunk_count mismatch"):
        validate_snapshot_readiness_pair(snapshot, bad)


def test_surface_readiness_requires_contract_panel_not_only_quotes() -> None:
    artifacts = {
        "clean_option_quotes_panel": {"records": [{
            "contract_key": "A", "underlying": "XYZ", "option_type": "CALL", "strike": 100,
            "expiration_date": "2024-06-21", "date": "2024-01-01",
            "available_at": "2024-01-01T00:00:00Z", "source_id": "fixture", "lineage_id": "l1", "iv": 0.2,
        }]},
        "clean_underlying_panel": {"records": [{
            "underlying": "XYZ", "date": "2024-01-01", "available_at": "2024-01-01T00:00:00Z",
            "close": 100, "source_id": "fixture", "lineage_id": "l1",
        }]},
    }
    _, _, _, readiness = MarketViewBindingBuilder().build(snapshot_id="snapshot-1", artifacts=artifacts)
    assert "get_surface_diagnostics" in readiness.blocked_operations


def test_surface_diagnostics_preserve_strike_price_alignment_and_aggregate_duplicates() -> None:
    rows = (
        {"expiration_date": "2024-06-21", "option_type": "CALL", "strike": 90, "iv": 0.30, "bid": 12, "ask": 14},
        {"expiration_date": "2024-06-21", "option_type": "CALL", "strike": None, "iv": 0.25, "bid": 99, "ask": 101},
        {"expiration_date": "2024-06-21", "option_type": "CALL", "strike": 100, "iv": 0.20, "bid": 7, "ask": 9},
        {"expiration_date": "2024-06-21", "option_type": "CALL", "strike": 100, "iv": 0.22, "bid": 5, "ask": 7},
        {"expiration_date": "2024-06-21", "option_type": "CALL", "strike": 110, "iv": 0.24, "bid": 3, "ask": 5},
    )
    summary = build_surface_summary(
        underlying="XYZ", decision_time=datetime(2024, 1, 1, tzinfo=UTC),
        quote_rows=rows, spot=100.0, minimum_strikes_per_expiry=3,
    )
    item = summary.slices[0]
    assert item.strike_count == 3
    assert item.price_monotonicity_violations == 0
    assert item.atm_iv == pytest.approx(0.21)


def test_reverse_dcf_reports_unbracketed_target_instead_of_false_solution() -> None:
    result = reverse_dcf(ReverseDcfAssumptions(
        market_price=10_000.0, base_free_cash_flow=100.0, discount_rate=0.10,
        terminal_growth_rate=0.02, forecast_years=5, shares_outstanding=10.0,
        lower_growth=-0.10, upper_growth=0.20,
    ))
    assert result["target_bracketed"] is False
    assert result["implied_annual_growth"] in {-0.10, 0.20}
    assert abs(float(result["valuation_residual"])) > 0


def test_macro_observation_builder_rejects_catalog_readiness_count_drift() -> None:
    module = importlib.import_module(
        "quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules."
        "P3_S37_M02_macro_observation_vintage_handler_bundle_builder"
    )
    series = MacroSeriesDefinition(
        series_id="CPI", title="CPI", region="US", country="US", family="INFLATION",
        unit="INDEX", frequency=Frequency.MONTHLY, source_id="fixture", release_id="CPI_RELEASE",
        vintage_support=True,
    )
    catalog = MacroSeriesReleaseCatalog(
        snapshot_id="snapshot-1", records=(series,), content_hash=content_hash(series.model_dump(mode="json")),
    )
    readiness_base = {
        "snapshot_id": "snapshot-1", "status": ViewReadinessStatus.READY,
        "available_operations": ("get_observations",), "blocked_operations": (),
        "available_fields": ("series_id",), "series_count": 2, "observation_count": 1,
        "vintage_capable_series_count": 1, "reason_codes": (),
    }
    readiness = MacroViewReadinessReport(content_hash=content_hash(readiness_base), **readiness_base)
    with pytest.raises(ValueError, match="series_count"):
        asyncio.run(module.execute({
            "macro_series_release_catalog": catalog.model_dump(mode="json"),
            "macro_view_readiness_report": readiness.model_dump(mode="json"),
        }, None))


def test_capability_level_thresholds_cannot_overlap() -> None:
    from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.capability_configs import (
        CapabilityProfilePolicyConfig,
    )
    base = yaml.safe_load((ROOT / "config/research_tools/CAPABILITY_PROFILE_POLICY.yaml").read_text(encoding="utf-8"))
    CapabilityProfilePolicyConfig.model_validate(base, strict=False)
    overlapping = dict(base)
    overlapping["level_thresholds"] = dict(base["level_thresholds"])
    overlapping["level_thresholds"]["STANDARD"] = overlapping["level_thresholds"]["BASIC"]
    with pytest.raises(ValueError, match="strictly increasing"):
        CapabilityProfilePolicyConfig.model_validate(overlapping, strict=False)
