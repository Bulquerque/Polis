from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s04_performance_risk.resource_access import (
    read_registry,
    read_schema,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.return_models import (
    QualifiedBacktestInput,
)
from quant_pipeline.phase_09.subphases.s04_performance_risk.service import (
    S4AnalyticsRequest,
    S4AnalyticsResult,
)

ROOT = Path(__file__).resolve().parent


def test_all_json_schemas_are_valid_draft_2020_12():
    schemas = sorted((ROOT / "schemas").glob("*.json"))
    assert len(schemas) >= 80
    for path in schemas:
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_installed_resource_access_reads_schema_and_registry():
    schema = json.loads(read_schema("S4AnalyticsRequest.schema.json"))
    registry = json.loads(read_registry("MODULE_REGISTRY.json"))
    assert schema["title"] == "S4AnalyticsRequest"
    assert len(registry["modules"]) == 8


def test_positive_fixtures_round_trip():
    qualified = QualifiedBacktestInput.model_validate_json(
        (ROOT / "fixtures/positive/qualified_backtest_input.json").read_text(encoding="utf-8")
    )
    request = S4AnalyticsRequest.model_validate_json(
        (ROOT / "fixtures/positive/s4_analytics_request.json").read_text(encoding="utf-8")
    )
    result = S4AnalyticsResult.model_validate_json(
        (ROOT / "fixtures/positive/s4_analytics_result.json").read_text(encoding="utf-8")
    )
    assert qualified.handoff.handoff_id == request.qualified_backtest.handoff.handoff_id
    assert result.quality.panel.identity.handoff_id == qualified.handoff.handoff_id


def test_adversarial_fixture_is_rejected():
    with pytest.raises(ValidationError):
        QualifiedBacktestInput.model_validate_json(
            (ROOT / "fixtures/adversarial/qualified_backtest_wrong_hash.json").read_text(
                encoding="utf-8"
            )
        )
