from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import FormatChecker
from jsonschema.validators import Draft202012Validator

from quant_pipeline.phase_07_strategy_tournament.finalization.runner import run_s8

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.contract
def test_all_s8_outputs_validate_against_exported_schemas(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    mapping = {
        "ranked_strategy_candidate_panel": "ranked_strategy_candidate_panel.schema.yaml",
        "ranking_tie_report": "ranking_tie_report.schema.yaml",
        "ranking_group_summary_panel": "ranking_group_summary_panel.schema.yaml",
        "strategy_thesis_card_panel": "strategy_thesis_card_panel.schema.yaml",
        "ranking_trace_panel": "ranking_trace_panel.schema.yaml",
        "ranking_audit_report": "ranking_audit_report.schema.yaml",
        "ranked_strategy_execution_context_snapshot": "ranked_strategy_execution_context_snapshot.schema.yaml",
        "compatibility_projection_report": "compatibility_projection_report.schema.yaml",
        "phase8_strategy_ranking_handoff_manifest": "phase8_strategy_ranking_handoff_manifest.schema.yaml",
    }
    for artifact, schema_name in mapping.items():
        schema = yaml.safe_load((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(output[artifact])


@pytest.mark.replay
def test_fixture_replay_is_deterministic(s8_input, s8_config):
    output = run_s8(s8_input, s8_config)
    expected = json.loads((ROOT / "fixtures/output/s8_output_fixture.json").read_text(encoding="utf-8"))
    for key in expected:
        if key == "module_execution_receipts":
            continue
        assert output[key] == expected[key], key
