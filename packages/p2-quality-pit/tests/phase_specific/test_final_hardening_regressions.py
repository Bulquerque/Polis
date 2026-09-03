from __future__ import annotations

import pytest

from quant_pipeline.phase_02_quality_pit.modules._option_identity import (
    canonical_economic_contract_key,
    resolve_canonical_contract_key,
)
from quant_pipeline.phase_02_quality_pit.modules._s2_temporal import parse_as_of_cutoff
from quant_pipeline.phase_02_quality_pit.profiles import strict_production_config
from quant_pipeline.phase_02_quality_pit.s6_quality import _temporal_issues
from quant_pipeline.phase_02_quality_pit.s6_handoff import validate_quality_gate
from quant_pipeline.phase_02_quality_pit.modules._module_executor import ContractValidationError


def test_s2_s4_share_same_economic_option_identity():
    row = {
        "canonical_instrument_id": "inst1:test",
        "underlying": "AAPL",
        "expiration_date": "2026-12-18",
        "strike": "100.000",
        "option_type": "CALL",
    }
    expected = canonical_economic_contract_key(row, row["canonical_instrument_id"])
    resolved, mode, reasons = resolve_canonical_contract_key(row)
    assert resolved == expected
    assert mode == "ECONOMIC"
    assert reasons == []


def test_date_only_as_of_is_end_of_day_in_quality_gate():
    rows = [{"available_at": "2026-07-23T21:00:00Z", "as_of_date": "2026-07-23"}]
    issues = _temporal_issues("clean_underlying_panel", rows, {})
    assert not [issue for issue in issues if issue.code == "P2Q_FUTURE_DATA"]
    assert parse_as_of_cutoff("2026-07-23", {}).hour == 23


def test_strict_production_profile_is_fail_closed():
    config = strict_production_config()
    assert config["strict_physical_validation"] is True
    assert config["strict_temporal_validation"] is True
    assert config["strict_source_quality"] is True
    assert config["strict_schema_validation"] is True
    assert config["allow_degraded_handoffs"] is False
    assert config["allow_legacy_unverified"] is False
    assert config["strict_target_readiness"] is True


def test_legacy_handoff_keeps_target_block_explicit_without_promoting_it():
    report = {
        "status": "PASS",
        "target_readiness": {
            "phase_03_agents_rag_memory": {"status": "BLOCK"},
            "phase_04_feature_base": {"status": "PASS"},
        },
    }
    status, readiness = validate_quality_gate(report, {})
    assert status == "PASS"
    assert readiness["phase_03_agents_rag_memory"]["status"] == "BLOCK"

    with pytest.raises(ContractValidationError, match="target readiness BLOCK"):
        validate_quality_gate(report, {"strict_target_readiness": True})
