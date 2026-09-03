from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.agent3_integration import (
    Agent3IntegratedBundle,
    parse_lifecycle_context_json,
    parse_risk_bundle_json,
    run_agent3,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
S5_TIME = datetime(2026, 8, 3, 18, 0, 1, tzinfo=UTC)
S6_TIME = datetime(2026, 8, 3, 18, 0, 2, tzinfo=UTC)


def load_inputs():
    risk = parse_risk_bundle_json((ROOT / "fixtures/risk_bundle.json").read_bytes())
    context = parse_lifecycle_context_json((ROOT / "fixtures/s6_context.json").read_bytes())
    return risk, context


def _portable_semantic_projection(value):
    """Remove environment metadata and integrity digests from portable golden comparison.

    Exact bitwise qualification is covered by the W6 qualification lock. This
    projection checks economic/contract semantics across compatible solver patch
    versions without hiding changes in quantities, objectives, constraints or states.
    """
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            if key == "solver_version" or key == "message":
                continue
            if key == "content_sha256" or key.endswith("_hash") or key.endswith("_sha256"):
                continue
            out[key] = _portable_semantic_projection(child)
        return out
    if isinstance(value, list):
        return [_portable_semantic_projection(item) for item in value]
    return value


def test_integrated_chain_matches_portable_semantic_golden():
    risk, context = load_inputs()
    result = run_agent3(
        risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME
    )
    expected_s5 = json.loads((ROOT / "fixtures/s5_result.json").read_text(encoding="utf-8"))
    expected_s6 = json.loads((ROOT / "fixtures/s6_result.json").read_text(encoding="utf-8"))
    assert _portable_semantic_projection(result.payload.s5_result.model_dump(mode="json")) == _portable_semantic_projection(expected_s5)
    assert _portable_semantic_projection(result.payload.s6_authorization.model_dump(mode="json")) == _portable_semantic_projection(expected_s6)


def test_integrated_chain_matches_golden_component_results():
    risk, context = load_inputs()
    result = run_agent3(
        risk,
        context,
        s5_processing_time=S5_TIME,
        s6_processing_time=S6_TIME,
    )
    expected_s5 = json.loads((ROOT / "fixtures/s5_result.json").read_text(encoding="utf-8"))
    expected_s6 = json.loads((ROOT / "fixtures/s6_result.json").read_text(encoding="utf-8"))
    assert result.payload.s5_result.model_dump(mode="json") == expected_s5
    assert result.payload.s6_authorization.model_dump(mode="json") == expected_s6
    assert result.envelope.content_sha256 == canonical_sha256(result.payload)
    assert result.payload.integration_receipts[-1] == "P8.S6:PUBLIC_API_EXECUTED"


def test_integrated_chain_is_deterministic():
    risk, context = load_inputs()
    first = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    second = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    assert first == second
    assert first.envelope.content_sha256 == second.envelope.content_sha256


def test_s6_time_cannot_precede_s5_time():
    risk, context = load_inputs()
    with pytest.raises(ValueError, match="cannot precede"):
        run_agent3(risk, context, s5_processing_time=S6_TIME, s6_processing_time=S5_TIME)


def test_processing_times_must_be_timezone_aware():
    risk, context = load_inputs()
    naive = datetime(2026, 8, 3, 18, 0, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        run_agent3(risk, context, s5_processing_time=naive, s6_processing_time=S6_TIME)


def test_json_boundary_rejects_extra_fields():
    raw = json.loads((ROOT / "fixtures/risk_bundle.json").read_text(encoding="utf-8"))
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        parse_risk_bundle_json(json.dumps(raw))


def test_integrated_schema_is_closed_and_accepts_result():
    risk, context = load_inputs()
    result = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    schema = yaml.safe_load((ROOT / "schemas/p8_agent_3_s5_s6_result_v1.schema.yaml").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result.model_dump(mode="json"))


def test_integrated_model_detects_chain_mismatch():
    risk, context = load_inputs()
    result = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    bad_s6 = result.payload.s6_authorization.model_copy(
        update={"envelope": result.payload.s6_authorization.envelope.model_copy(update={"run_id": "OTHER"})}
    )
    with pytest.raises(ValidationError, match="run ID mismatch"):
        Agent3IntegratedBundle(
            envelope=result.envelope,
            payload=result.payload.model_copy(update={"s6_authorization": bad_s6}),
        )


def test_namespace_root_is_not_regular_package():
    assert not (ROOT / "src/quant_pipeline/__init__.py").exists()

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cycle_id", 99, "cycle ID mismatch"),
        ("decision_time", datetime(2026, 8, 3, 18, 0, 0, 500000, tzinfo=UTC), "decision time mismatch"),
    ],
)
def test_integrated_model_detects_envelope_mismatches(field, value, message):
    risk, context = load_inputs()
    result = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    bad_envelope = result.payload.s6_authorization.envelope.model_copy(update={field: value})
    bad_s6 = result.payload.s6_authorization.model_copy(update={"envelope": bad_envelope})
    with pytest.raises(ValidationError, match=message):
        Agent3IntegratedBundle(
            envelope=result.envelope,
            payload=result.payload.model_copy(update={"s6_authorization": bad_s6}),
        )


def test_integrated_model_detects_snapshot_mismatch():
    risk, context = load_inputs()
    result = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    bad_payload = result.payload.s6_authorization.payload.model_copy(
        update={"decision_snapshot_hash": "2" * 64}
    )
    bad_s6 = result.payload.s6_authorization.model_copy(update={"payload": bad_payload})
    with pytest.raises(ValidationError, match="decision snapshot mismatch"):
        Agent3IntegratedBundle(
            envelope=result.envelope,
            payload=result.payload.model_copy(update={"s6_authorization": bad_s6}),
        )


def test_integrated_model_detects_s6_result_predating_s5():
    risk, context = load_inputs()
    result = run_agent3(risk, context, s5_processing_time=S5_TIME, s6_processing_time=S6_TIME)
    early = datetime(2026, 8, 3, 18, 0, 0, tzinfo=UTC)
    bad_envelope = result.payload.s6_authorization.envelope.model_copy(
        update={"available_at": early, "computed_at": early, "recorded_at": early}
    )
    bad_s6 = result.payload.s6_authorization.model_copy(update={"envelope": bad_envelope})
    with pytest.raises(ValidationError, match="cannot predate"):
        Agent3IntegratedBundle(
            envelope=result.envelope,
            payload=result.payload.model_copy(update={"s6_authorization": bad_s6}),
        )
