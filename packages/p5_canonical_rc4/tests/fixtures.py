"""Deterministic native P4 V14.9 fixtures for full P5 integration tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sin
from typing import Any

from quant_pipeline.phase_05_underlying_forecasts.boundary import canonical_sha256

P4_VERSION = "v14.9-rc1"
P4_PHASE = "phase_04_feature_base"


def _envelope(
    name: str,
    records: list[dict[str, Any]],
    *,
    run_id: str,
    cycle_id: str,
    as_of_time: datetime,
    created_at: datetime,
    module_id: str,
    grain: list[str],
    metadata: dict[str, Any] | None = None,
    execution_status: str = "PRODUCED",
    quality_status: str = "VALIDATED",
    alias_of: str | None = None,
) -> dict[str, Any]:
    meta = metadata or {}
    content_hash = canonical_sha256({"records": records, "metadata": meta, "alias_of": alias_of})
    return {
        "artifact_id": f"{name}:{content_hash[:16]}",
        "artifact_name": name,
        "schema_version": P4_VERSION,
        "producer_phase": P4_PHASE,
        "producer_module_id": module_id,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_of_time.isoformat(),
        "created_at": created_at.isoformat(),
        "content_hash": content_hash,
        "record_count": len(records),
        "grain": grain,
        "lineage_id": canonical_sha256([name, run_id, cycle_id, as_of_time.isoformat()]),
        "execution_status": execution_status,
        "quality_status": quality_status,
        "records": records,
        "metadata": meta,
        "alias_of": alias_of,
    }


def _reference(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_name": artifact["artifact_name"],
        "artifact_id": artifact["artifact_id"],
        "content_hash": artifact["content_hash"],
        "record_count": artifact["record_count"],
        "execution_status": artifact["execution_status"],
    }


def _handoff_row(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_name": artifact["artifact_name"],
        "artifact_id": artifact["artifact_id"],
        "content_hash": artifact["content_hash"],
        "schema_version": artifact["schema_version"],
        "record_count": artifact["record_count"],
        "grain": artifact["grain"],
        "execution_status": artifact["execution_status"],
        "quality_status": artifact["quality_status"],
        "fit_state_ids": [],
        "limitations": [],
        "period_start": None,
        "period_end": None,
    }


def build_fixture(days: int = 160) -> dict[str, Any]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    underlyings = ("AAA", "BBB", "CCC")
    run_id, cycle_id = "p4-run-v149-001", "cycle-001"
    as_of_time = start + timedelta(days=days - 1)
    p4_created_at = as_of_time + timedelta(minutes=5)
    generated_at = p4_created_at + timedelta(minutes=5)

    selected_rows: list[dict[str, Any]] = []
    pca_rows: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    materialized_rows: list[dict[str, Any]] = []
    feature_ids = (
        "perspective.momentum.time_series",
        "perspective.reversion.short_term",
        "perspective.risk.multiscale",
        "perspective.risk.downside",
        "perspective.risk.drawdown_stress",
        "perspective.liquidity.price_impact",
        "options.atm_implied_volatility",
        "perspective.macro.growth_state",
        "perspective.macro.inflation_state",
        "perspective.structure.common_mode_proxy",
        "perspective.structure.contagion_pressure_proxy",
        "perspective.carry.curve_slope_state",
    )
    catalog = {
        f"SHORT|{feature_id}": {
            "feature_id": feature_id,
            "family_id": "F01" if "momentum" in feature_id or "reversion" in feature_id else "F07",
            "source_modalities": ["MARKET" if not feature_id.startswith("options.") else "OPTIONS"],
            "parameterization_id": "fixture-v149",
            "implementation_tier": "FOUNDATIONAL",
            "lineage_id": f"feature-lineage-{index}",
        }
        for index, feature_id in enumerate(feature_ids)
    }
    for day in range(days):
        decision_time = start + timedelta(days=day)
        for index, underlying in enumerate(underlyings):
            base = 0.006 * sin(day / 5 + index) + 0.0015 * (index - 1)
            shock = 0.002 * sin(day / 2.7 + index * 0.3)
            return_state = base + shock
            future_return = 0.45 * return_state + 0.003 * sin((day + 1) / 4 + index)
            values = {
                "perspective.momentum.time_series": return_state,
                "perspective.reversion.short_term": -0.4 * return_state,
                "perspective.risk.multiscale": abs(return_state) + 0.004,
                "perspective.risk.downside": max(-return_state, 0.0) + 0.001,
                "perspective.risk.drawdown_stress": max(-base, 0.0),
                "perspective.liquidity.price_impact": 0.05 + 0.01 * index + abs(shock),
                "options.atm_implied_volatility": 0.18 + 0.02 * index + abs(return_state) * 2.0,
                "perspective.macro.growth_state": 0.5 * sin(day / 10),
                "perspective.macro.inflation_state": 0.3 * sin(day / 13 + 0.2),
                "perspective.structure.common_mode_proxy": 0.2 + 0.1 * sin(day / 8),
                "perspective.structure.contagion_pressure_proxy": 0.1 + abs(shock),
                "perspective.carry.curve_slope_state": 0.25 + 0.02 * sin(day / 12),
            }
            lineage = f"p4-v149-lineage-{underlying}-{day}"
            selected_rows.append({
                "decision_time": decision_time.isoformat(),
                "available_at": decision_time.isoformat(),
                "entity_id": underlying,
                "horizon_group": "SHORT",
                "values": values,
                "raw_values": values,
                "transformed_values": values,
                "normalized_values": values,
                "neutralized_values": values,
                "missingness_mask": {name: False for name in values},
                "feature_state_ids": {name: f"state-{name}-{day}" for name in values},
                "quality_state": "PASS",
                "lineage_id": lineage,
            })
            pca_rows.append({
                "decision_time": decision_time.isoformat(),
                "available_at": decision_time.isoformat(),
                "entity_id": underlying,
                "family_id": "F01",
                "horizon_group": "SHORT",
                "component_values": [return_state, abs(return_state)],
                "representation_type": "PCA",
                "fit_state_id": "pca-fit-fixture",
                "fold_id": "fold-fixture",
                "lineage_id": f"pca-lineage-{underlying}-{day}",
            })
            materialized_rows.append({
                "underlying": underlying,
                "decision_time": decision_time.isoformat(),
                "as_of_time": decision_time.isoformat(),
                "available_at": decision_time.isoformat(),
                "horizon_group": "SHORT",
                "features": values,
                "missingness_mask": {name: False for name in values},
                "feature_state_ids": {name: f"state-{name}-{day}" for name in values},
                "quality_state": "PASS",
                "lineage_id": lineage,
            })
            outcomes.append({
                "underlying": underlying,
                "prediction_timestamp": decision_time.isoformat(),
                "label_end_time": (decision_time + timedelta(days=1)).isoformat(),
                "available_at": (decision_time + timedelta(days=1)).isoformat(),
                "target_id": "excess_return_1d",
                "horizon": "1D",
                "unit": "decimal_return",
                "value": future_return,
                "lineage_id": f"outcome-lineage-{underlying}-{day}",
            })

    artifacts: dict[str, dict[str, Any]] = {}
    artifacts["underlying_feature_matrix_raw"] = _envelope(
        "underlying_feature_matrix_raw", [], run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S9.M04",
        grain=["alias_of"], metadata={}, execution_status="PRODUCED", quality_status="VALIDATED",
    )
    artifacts["underlying_feature_matrix_selected"] = _envelope(
        "underlying_feature_matrix_selected", selected_rows, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S7.M04",
        grain=["decision_time", "entity_id", "horizon_group"], metadata={"feature_catalog": catalog},
    )
    artifacts["underlying_feature_factors_pca"] = _envelope(
        "underlying_feature_factors_pca", pca_rows, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S8.M02",
        grain=["decision_time", "entity_id", "family_id", "horizon_group"], metadata={},
    )
    artifacts["underlying_feature_embeddings"] = _envelope(
        "underlying_feature_embeddings", [], run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S8.M03",
        grain=["decision_time", "entity_id", "family_id", "horizon_group"], metadata={},
        execution_status="SKIPPED_NOT_AUTHORIZED", quality_status="NOT_EVALUATED",
    )
    for name, module, grain in (
        ("feature_selection_report", "P4.S7.M04", ["feature_id", "horizon_group"]),
        ("feature_lineage_report", "P4.S9.M01", ["feature_id", "horizon_group"]),
        ("drift_safety_report", "P4.S9.M02", ["gate_scope", "scope_id"]),
        ("representation_fold_plan", "P4.S8.M01", ["fold_id"]),
    ):
        records = [{"record_id": f"{name}-fixture", "status": "PASS"}] if name != "representation_fold_plan" else [
            {"fold_id": "fold-fixture", "fit_end_time": (start + timedelta(days=50)).isoformat()}
        ]
        artifacts[name] = _envelope(
            name, records, run_id=run_id, cycle_id=cycle_id, as_of_time=as_of_time,
            created_at=p4_created_at, module_id=module, grain=grain, metadata={},
        )

    view_specs = [
        ("TABULAR_INTERPRETABLE", ["underlying_feature_matrix_selected"], [], "preserve_explicit_mask", ["decision_time", "entity_id", "horizon_group"]),
        ("CROSS_SECTIONAL_RANKED", ["underlying_feature_matrix_selected"], ["normalized_values"], "preserve_explicit_mask", ["decision_time", "entity_id", "horizon_group"]),
        ("SEQUENCE_MULTI_HORIZON", ["underlying_feature_matrix_selected", "representation_fold_plan"], [], "mask_and_age_of_information", ["entity_id", "decision_time", "horizon_group"]),
        ("LATENT_FAMILY", ["underlying_feature_factors_pca", "underlying_feature_embeddings"], [], "encoder_may_be_explicitly_skipped", ["decision_time", "entity_id", "family_id", "horizon_group"]),
        ("SPARSE_MODALITY_AWARE", ["underlying_feature_matrix_selected"], ["missingness_mask", "source_modalities"], "first_class_input", ["decision_time", "entity_id", "horizon_group"]),
    ]
    manifest_records, bundle_records = [], []
    for view_id, names, filters, missingness, grain in view_specs:
        manifest_records.append({
            "view_id": view_id, "artifact_ids": [artifacts[name]["artifact_id"] for name in names],
            "execution_status": "PRODUCED", "feature_filters": filters, "grain": grain,
            "limitations": [], "materialized": False, "missingness_policy": missingness,
        })
        bundle_records.append({
            "view_id": view_id, "artifact_references": [_reference(artifacts[name]) for name in names],
            "execution_status": "PRODUCED", "payload_copied": False,
        })
    view_manifest = _envelope(
        "model_consumer_view_manifest", manifest_records, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S9.M03",
        grain=["view_id"], metadata={"contains_predictions": False, "blocked_families": []},
    )
    view_bundle = _envelope(
        "model_consumer_view_bundle", bundle_records, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S9.M03",
        grain=["view_id"], metadata={"contains_payload_copies": False},
    )
    gate_records = [{
        "gate_scope": "HANDOFF", "scope_id": "P4_TO_P5", "decision": "PASS",
        "block_count": 0, "warn_count": 0, "reason_codes": [],
        "minimum_required_features": 1, "selected_feature_count": len(feature_ids),
    }]
    quality_gate = _envelope(
        "p4_quality_gate_decision", gate_records, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=p4_created_at, module_id="P4.S9.M02",
        grain=["gate_scope", "scope_id"], metadata={"final_decision": "PASS"},
    )
    handoff_names = (
        "underlying_feature_matrix_raw", "underlying_feature_matrix_selected",
        "underlying_feature_factors_pca", "underlying_feature_embeddings",
        "feature_selection_report", "feature_lineage_report", "drift_safety_report",
    )
    handoff = _envelope(
        "phase5_feature_handoff_manifest", [_handoff_row(artifacts[name]) for name in handoff_names],
        run_id=run_id, cycle_id=cycle_id, as_of_time=as_of_time, created_at=p4_created_at,
        module_id="P4.S9.M04", grain=["artifact_name"], metadata={
            "destination_phase": "phase_05_underlying_forecasts",
            "gate_decision": "PASS", "completeness_status": "COMPLETE",
            "consumer_view_manifest_id": view_manifest["artifact_id"],
            "consumer_view_manifest_hash": view_manifest["content_hash"],
        },
    )

    materialized_views = [
        {
            "view_id": view_id,
            "grain": ["underlying", "decision_time", "horizon_group"],
            "records": materialized_rows,
            "missingness_policy": "EXPLICIT_MASK",
            "lineage_id": f"view-lineage-{view_id}",
            "quality_state": "PASS",
        }
        for view_id in ("TABULAR_INTERPRETABLE", "SEQUENCE_MULTI_HORIZON", "TAIL_RISK_SPECIALIST", "REGIME_CONTEXT", "GRAPH_RELATIONAL")
    ]
    passports = {"records": [{
        "hypothesis_id": "H01", "status": "FOUNDATIONAL", "family_id": "F01",
        "hypothesis_name": "absolute_momentum", "mechanism": "absolute momentum",
        "expected_sign": "CONTEXT_DEPENDENT", "falsification_rule": "sealed OOS gate",
        "primary_horizon": "SHORT", "max_parameterizations": 3,
    }]}
    conflicts = {"records": [{
        "entity_id": underlying, "decision_time": as_of_time.isoformat(),
        "available_at": as_of_time.isoformat(), "group_id": "momentum_direction",
        "horizon_group": "SHORT", "conflict_score": 0.1 + 0.05 * index,
        "consensus_score": 0.8 - 0.05 * index, "dispersion_score": 0.1,
        "entropy_score": 0.2, "minority_view_strength": 0.1,
        "quality_state": "PASS", "missingness_state": "OBSERVED",
        "source_modalities": ["MARKET"], "record_lineage_id": f"conflict-{underlying}",
    } for index, underlying in enumerate(underlyings)]}
    return {
        "start": start, "as_of_time": as_of_time, "generated_at": generated_at,
        "phase5_feature_handoff_manifest": handoff,
        "model_consumer_view_manifest": view_manifest,
        "model_consumer_view_bundle": view_bundle,
        "p4_quality_gate_decision": quality_gate,
        "p4_artifact_catalog": artifacts,
        "authorized_consumer_view_registry_fixture": {"views": materialized_views},
        "approved_hypothesis_passport_registry": passports,
        "hypothesis_budget_report": {"records": [{"hypothesis_id": "H01", "limit": 3, "approved_count": 1, "status": "WITHIN_BUDGET"}]},
        "research_attempt_ledger": {"records": []},
        "rejected_feature_graveyard": {"records": []},
        "feature_observer_registry": {"records": []},
        "perspective_conflict_panel": conflicts,
        "p5_offline_training_outcome_bundle": {"records": outcomes},
        "representation_fold_plan": artifacts["representation_fold_plan"],
        "representation_quality_report": {"records": [], "quality_state": "PASS"},
        "drift_safety_report": artifacts["drift_safety_report"],
        "feature_transform_state_manifest": {"records": []},
    }
