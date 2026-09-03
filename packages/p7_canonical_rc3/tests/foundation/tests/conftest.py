from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256

DECISION = "2026-01-05T14:30:00Z"
CREATED = "2026-01-05T14:31:00Z"


def envelope(name: str, records: list[dict[str, Any]], *, grain: str = "one_record_per_candidate"):
    base = {
        "artifact_id": f"{name}:p6-run-1",
        "artifact_name": name,
        "schema_version": "2.0.0",
        "producer_phase": "P6",
        "producer_module_id": "P6.S10.M01",
        "destination_phase": "P7",
        "pipeline_version": "15.0.0",
        "run_id": "p6-run-1",
        "cycle_id": "cycle-2",
        "decision_time": DECISION,
        "available_at": DECISION,
        "created_at": CREATED,
        "record_count": len(records),
        "grain": grain,
        "lineage_id": "lin-p6-1",
        "capability_status": "AVAILABLE",
        "records": deepcopy(records),
    }
    return {**base, "content_sha256": content_sha256(base)}


def candidate_records():
    candidate = {
        "candidate_id": "cand-1",
        "cycle_id": "cycle-2",
        "decision_time": DECISION,
        "underlying_id": "XYZ",
        "horizon": "5_sessions",
        "objective_family": "RANGE",
        "market_snapshot_id": "snap-1",
        "lineage_id": "lin-cand-1",
        "strategy_class": "IRON_CONDOR",
        "capabilities": {
            "ambiguity": "UNAVAILABLE",
            "greeks": "UNAVAILABLE",
            "equivalence": "UNAVAILABLE",
            "quality_diversity": "UNAVAILABLE",
        },
    }
    common = {"candidate_id": "cand-1", "available_at": DECISION}
    return {
        "strategy_candidate_panel": [candidate],
        "strategy_leg_panel": [{**common, "leg_id": "leg-1"}],
        "strategy_market_snapshot": [{"market_snapshot_id": "snap-1", "market_snapshot_time": DECISION}],
        "strategy_payoff_panel": [{**common, "payoff_id": "pay-1"}],
        "strategy_scenario_evaluation_panel": [{**common, "scenario_id": "scenario-1"}],
        "strategy_risk_panel": [{**common, "maximum_loss": 100.0}],
        "strategy_cost_liquidity_panel": [{**common, "entry_cost": 10.0}],
        "strategy_lineage_panel": [{**common, "lineage_id": "lin-cand-1"}],
        "strategy_generation_trace_panel": [{**common, "trace_id": "trace-1"}],
        "candidate_rejection_report": [],
        "candidate_generation_audit": [{"status": "PASS", "available_at": DECISION}],
    }


@pytest.fixture
def module_config():
    return {
        "context": {
            "pipeline_version": "15.0.0",
            "run_id": "p6-run-1",
            "cycle_id": "cycle-2",
            "decision_time": DECISION,
            "created_at": CREATED,
            "lineage_id": "lin-p7-s1",
        },
        "policy": {},
    }


@pytest.fixture
def p6_fixture():
    artifacts = [envelope(name, records, grain="one_record_per_market_snapshot" if name == "strategy_market_snapshot" else "one_record_per_candidate") for name, records in candidate_records().items()]
    refs = [
        {
            "artifact_name": item["artifact_name"],
            "artifact_id": item["artifact_id"],
            "content_sha256": item["content_sha256"],
            "schema_version": item["schema_version"],
            "record_count": item["record_count"],
            "required": True,
            "grain": item["grain"],
        }
        for item in artifacts
    ]
    manifest = {
        "manifest_id": "p6-to-p7-manifest-1",
        "contract_version": "2.0.0",
        "schema_version": "2.0.0",
        "producer_phase": "P6",
        "destination_phase": "P7",
        "pipeline_version": "15.0.0",
        "run_id": "p6-run-1",
        "cycle_id": "cycle-2",
        "decision_time": DECISION,
        "created_at": CREATED,
        "artifacts": refs,
    }
    return manifest, artifacts

from pathlib import Path
import yaml

from quant_pipeline.phase_07_strategy_tournament.foundation.artifacts import create_artifact
from quant_pipeline.phase_07_strategy_tournament.foundation.models import ModuleContext

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"


def load_registry(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG_ROOT / name).read_text(encoding="utf-8"))


def s2_candidate_record(
    candidate_id: str = "cand-1",
    *,
    objective_family: str = "RANGE",
    strategy_class: str = "IRON_CONDOR",
    maximum_loss: float = 100.0,
    currency: str = "USD",
    calendar_id: str = "XNYS",
    scenario_count: int = 2,
) -> dict[str, Any]:
    candidate = {
        "candidate_id": candidate_id,
        "cycle_id": "cycle-2",
        "decision_time": DECISION,
        "underlying_id": "XYZ",
        "horizon": "5_sessions",
        "objective_family": objective_family,
        "market_snapshot_id": "snap-1",
        "lineage_id": f"lin-{candidate_id}",
        "strategy_class": strategy_class,
        "currency": currency,
        "capabilities": {
            "ambiguity": "UNAVAILABLE",
            "greeks": "UNAVAILABLE",
            "equivalence": "UNAVAILABLE",
            "quality_diversity": "UNAVAILABLE",
        },
    }
    common = {"candidate_id": candidate_id, "available_at": DECISION}
    return {
        "candidate_id": candidate_id,
        "cycle_id": "cycle-2",
        "decision_time": DECISION,
        "underlying_id": "XYZ",
        "horizon": "5_sessions",
        "objective_family": objective_family,
        "market_snapshot_id": "snap-1",
        "lineage_id": f"lin-{candidate_id}",
        "candidate": candidate,
        "legs": [{**common, "leg_id": f"leg-{candidate_id}"}],
        "payoffs": [{**common, "payoff_id": f"pay-{candidate_id}"}],
        "scenario_evaluations": [
            {**common, "scenario_id": f"scenario-{index}"}
            for index in range(scenario_count)
        ],
        "generation_trace": [{**common, "trace_id": f"trace-{candidate_id}"}],
        "risk": {
            **common,
            "maximum_loss": maximum_loss,
            "maximum_loss_units": "currency",
            "maximum_loss_proven": True,
            "expected_net_payoff": 12.0,
            "expected_net_payoff_units": "currency",
            "expected_shortfall": 25.0,
            "expected_shortfall_units": "currency",
            "probability_of_profit": 0.62,
            "probability_of_profit_units": "probability",
            "return_on_max_loss": 0.12,
            "return_on_max_loss_units": "ratio",
            "payoff_fit_error": 0.03,
            "payoff_fit_error_units": "squared_error",
        },
        "cost_liquidity": {
            **common,
            "entry_cost": 10.0,
            "entry_cost_units": "currency",
            "liquidity_score": 0.8,
            "liquidity_score_units": "normalized_score",
            "currency": currency,
        },
        "lineage": {**common, "lineage_id": f"lin-{candidate_id}"},
        "market_snapshot": {
            "market_snapshot_id": "snap-1",
            "market_snapshot_time": DECISION,
            "currency": currency,
            "calendar_id": calendar_id,
        },
        "ambiguity_evaluations": [],
        "greeks": [],
        "equivalence": [],
        "quality_diversity": [],
    }


def make_internal_artifact(name: str, records: list[dict[str, Any]], module_config, *, grain: str):
    context = ModuleContext.model_validate(module_config["context"])
    return create_artifact(
        artifact_name=name,
        records=records,
        producer_module_id="TEST.FIXTURE",
        context=context,
        grain=grain,
        capability_status="AVAILABLE" if records else "UNAVAILABLE",
    ).model_dump(mode="json")


@pytest.fixture
def s2_registries():
    return {
        "eligibility": load_registry("eligibility_policy_registry.yaml"),
        "comparison": load_registry("comparison_group_policy.yaml"),
        "metrics": load_registry("metric_semantics_registry.yaml"),
        "objectives": load_registry("objective_family_registry.yaml"),
    }


@pytest.fixture
def s2_inputs(module_config, s2_registries):
    candidate = s2_candidate_record()
    bundle = make_internal_artifact(
        "temporally_safe_candidate_bundle",
        [candidate],
        module_config,
        grain="one_record_per_candidate",
    )
    feedback = make_internal_artifact(
        "ranking_feedback_context",
        [],
        module_config,
        grain="one_record_per_promoted_feedback_item",
    )
    return bundle, feedback, s2_registries
