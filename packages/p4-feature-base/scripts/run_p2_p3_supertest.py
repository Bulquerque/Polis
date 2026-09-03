from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PACKAGE_ROOT.parents[1]
SRC = PACKAGE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(PACKAGE_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "tests"))

# The workspace co-installs P3 and P4 beneath the shared regular
# ``quant_pipeline`` package.  Extend the already-loaded namespace before
# importing the fixture helpers so this standalone runner behaves like the
# package test process.
import quant_pipeline  # noqa: E402

P4_NAMESPACE = str(SRC / "quant_pipeline")
if P4_NAMESPACE not in quant_pipeline.__path__:
    quant_pipeline.__path__.append(P4_NAMESPACE)

from full_pipeline_fixture import build_full_inputs  # noqa: E402
from quant_pipeline.phase_04_feature_base.integrated_runner import run_integrated_phase  # noqa: E402
from quant_pipeline.phase_04_feature_base.runtime.canonical import content_hash  # noqa: E402
from quant_pipeline.phase_04_feature_base.s8.decoder import decode_record, observed_rmse  # noqa: E402
from quant_pipeline.phase_04_feature_base.s8.artifacts import ArtifactEnvelope  # noqa: E402


LONG_PANEL = Path("reports/verification/p0_p1_p2_supertest/full_underlying_feature_panel.csv")
P3_ML_PANEL = Path("reports/verification/p0_p1_p2_supertest/p3_ml_feature_panel.csv")
P2_REPORT = Path("reports/verification/p0_p1_p2_supertest/p2_quality_report.json")
P3_REPORT = Path("reports/verification/p0_p1_p2_supertest/p3_canonical_integration.json")
BOUNDARY_REPORT = Path("reports/verification/p0_p1_p2_supertest/live_p2_p3_boundary.json")


def _json(value: Any) -> Any:
    if isinstance(value, ArtifactEnvelope):
        return value.model_dump(mode="json")
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso(value: str) -> str:
    return value.replace("Z", "+00:00")


def _artifact(name: str, records: list[dict[str, Any]], context: Any, **extra: Any) -> dict[str, Any]:
    return {
        "artifact_id": f"{name}-p2-p3-supertest",
        "created_at": context.created_at.isoformat(),
        "lineage_id": f"lineage:p2-p3-supertest:{name}",
        "pipeline_version": context.pipeline_version,
        "records": records,
        **extra,
    }


def _read_long_panel(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not source_rows:
        raise RuntimeError(f"empty longitudinal panel: {path}")
    required = {"date", "available_at", "past_return", "volatility", "document_event_score", "society_consensus", "target"}
    missing = required - set(source_rows[0])
    if missing:
        raise RuntimeError(f"longitudinal panel missing columns: {sorted(missing)}")
    prices: list[float] = []
    current = 100.0
    p4_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    for index, source in enumerate(source_rows):
        past_return = float(source["past_return"])
        if past_return <= -1.0:
            raise RuntimeError(f"invalid return at row {index}: {past_return}")
        current *= 1.0 + past_return
        prices.append(current)
        available_at = source["available_at"]
        close = current
        p4_rows.append(
            {
                "date": source["date"],
                "as_of_date": available_at,
                "available_at": available_at,
                "decision_time": available_at,
                "underlying": "LONG_PANEL",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "financial_volume": close,
                "bid": close,
                "ask": close,
                "adjustment_factor": 1.0,
                "is_trading_day": True,
                "source_id": "P2_P3_LONG_PANEL",
                "quality_flag": "PASS",
                "lineage_id": f"lineage:long-panel:{index}",
                "pipeline_version": "V14.9-RC1",
                "stable_sequence": index,
                "past_return": past_return,
                "volatility": float(source["volatility"]),
                "document_event_score": float(source["document_event_score"]),
                "society_consensus": float(source["society_consensus"]),
            }
        )
        target_rows.append(
            {
                "date": source["date"],
                "available_at": available_at,
                "target": float(source["target"]),
                "target_passed_to_p4": False,
            }
        )
    return p4_rows, target_rows


def _replace_live_inputs(inputs: dict[str, Any], context: Any, long_rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = copy.deepcopy(inputs)
    base_underlying = result["clean_underlying_panel"]
    result["clean_underlying_panel"] = _artifact(
        "clean_underlying_panel",
        list(base_underlying.get("records", [])) + long_rows,
        context,
    )

    social_rows = [
        {
            "date": row["date"],
            "as_of_date": row["as_of_date"],
            "available_at": row["available_at"],
            "decision_time": row["decision_time"],
            "underlying": row["underlying"],
            "social_feature_id": "society_consensus",
            "feature_name": "society_consensus",
            "feature_value": row["society_consensus"],
            "feature_type": "CONTINUOUS",
            "source_quality_score": 1.0,
            "evidence_count": max(0, int(round(row["document_event_score"]))),
            "agent_agreement_score": None,
            "agent_disagreement_score": None,
            "reference_date": row["date"],
            "pipeline_version": context.pipeline_version,
            "lineage_id": row["lineage_id"],
            "stable_sequence": row["stable_sequence"],
        }
        for row in long_rows
    ]
    base_social = result["social_feature_panel"]
    result["social_feature_panel"] = copy.deepcopy(base_social)
    result["social_feature_panel"]["artifact_id"] = "social_feature_panel-p2-p3-supertest"
    result["social_feature_panel"]["created_at"] = context.created_at.isoformat()
    result["social_feature_panel"]["lineage_id"] = "lineage:p2-p3-supertest:social_feature_panel"
    result["social_feature_panel"]["pipeline_version"] = context.pipeline_version
    result["social_feature_panel"]["run_id"] = context.run_id
    result["social_feature_panel"]["cycle_id"] = context.cycle_id
    result["social_feature_panel"]["as_of_time"] = context.as_of_time.isoformat()
    result["social_feature_panel"]["records"] = list(base_social.get("records", [])) + social_rows

    # Keep the handoff manifests aligned with the replaced artifacts.  The
    # supertest uses the manifests as contracts, not as a hidden data bundle.
    p2_handoff = result.get("phase4_handoff_manifest")
    if isinstance(p2_handoff, dict):
        p2_names = [
            key
            for key in result
            if key.startswith("clean_") or key == "quality_report_phase_2"
        ]
        p2_handoff["artifact_ids"] = [
            result[key]["artifact_id"] for key in p2_names
        ]
        p2_handoff["target_artifact_ids"] = list(p2_handoff["artifact_ids"])
        p2_handoff["artifact_refs"] = [
            {
                "artifact_name": key,
                "artifact_id": result[key]["artifact_id"],
                "schema_version": result[key].get("schema_version"),
                "lineage_id": result[key].get("lineage_id"),
                "row_count": len(result[key].get("records", [])),
            }
            for key in sorted(p2_names)
        ]
    p3_handoff = result.get("phase4_social_handoff_manifest")
    if isinstance(p3_handoff, dict):
        entries = []
        for entry in p3_handoff.get("entries", []):
            item = dict(entry)
            artifact_name = item.get("artifact_name")
            if artifact_name in result:
                source_artifact = result[artifact_name]
                item.update(
                    artifact_id=source_artifact["artifact_id"],
                    row_count=len(source_artifact.get("records", [])),
                    lineage_id=source_artifact["lineage_id"],
                    content_hash=content_hash(source_artifact),
                )
            entries.append(item)
        p3_handoff["entries"] = entries
    return result


def _source_entry(path: Path, phase: str, records: int, *, target_present: bool = False) -> dict[str, Any]:
    return {
        "path": str(path),
        "phase": phase,
        "sha256": _sha256(path),
        "record_count": records,
        "target_present_in_source": target_present,
        "target_passed_to_p4": False,
        "availability": "materialized_repository_artifact",
    }


def _time_key(value: str) -> str:
    return datetime.fromisoformat(_iso(value)).astimezone(timezone.utc).isoformat()


def _decoder_evidence(outputs: dict[str, Any]) -> dict[str, Any]:
    factors = outputs["underlying_feature_factors_pca"]
    states = outputs["pca_fit_state_manifest"]
    matrix = outputs["underlying_feature_matrix_selected"]
    factor_records = factors["records"]
    state_by_id = {record["fit_state_id"]: record for record in states["records"]}
    selected = next((item for item in factor_records if item["representation_type"] == "PCA"), None)
    if selected is None:
        raise RuntimeError("P4 produced no PCA factor record for decoder test")
    state = state_by_id[selected["fit_state_id"]]
    matrix_candidates = [
        record
        for record in matrix["records"]
        if _time_key(record["decision_time"]) == _time_key(selected["decision_time"])
        and str(record["entity_id"]) == str(selected["entity_id"])
        and str(record["horizon_group"]) == str(selected["horizon_group"])
        and all(feature_id in record.get("values", {}) for feature_id in state["feature_ids"])
    ]
    if not matrix_candidates:
        raise RuntimeError("selected matrix row for decoder test was not found")
    matrix_record = matrix_candidates[0]
    expected = []
    observed = []
    for feature_id, median in zip(state["feature_ids"], state["imputation_medians"], strict=True):
        value = matrix_record.get("values", {}).get(feature_id)
        is_observed = not bool(matrix_record.get("missingness_mask", {}).get(feature_id, value is None)) and value is not None
        expected.append(float(value) if is_observed else float(median))
        observed.append(is_observed)
    decoded = decode_record(selected, state)[0].tolist()
    rmse = observed_rmse(np.asarray([decoded]), np.asarray([expected]), np.asarray([observed]))
    direct = (
        np.asarray([selected["component_values"]], dtype=float)
        @ np.asarray(state["components"], dtype=float)
        + np.asarray(state["mean"], dtype=float)
    )
    equivalence_rmse = observed_rmse(np.asarray([decoded]), direct)
    reference_rmse = float(state["validation_reconstruction_rmse"])
    return {
        "status": "PASS" if math.isfinite(equivalence_rmse) and equivalence_rmse <= 1e-12 else "FAIL",
        "representation_type": selected["representation_type"],
        "fit_state_id": selected["fit_state_id"],
        "decision_time": selected["decision_time"],
        "entity_id": selected["entity_id"],
        "feature_ids": list(state["feature_ids"]),
        "expected_values": expected,
        "decoded_values": decoded,
        "observed_mask": observed,
        "decoder_rmse": rmse,
        "reference_rmse": reference_rmse,
        "decoder_formula_equivalence_rmse": equivalence_rmse,
        "tolerance": 1e-8,
        "decoder_implementation": "quant_pipeline.phase_04_feature_base.s8.decoder.decode_record",
    }


def run(workspace_root: Path, output_dir: Path) -> dict[str, Any]:
    long_path = workspace_root / LONG_PANEL
    p3_ml_path = workspace_root / P3_ML_PANEL
    p2_report_path = workspace_root / P2_REPORT
    p3_report_path = workspace_root / P3_REPORT
    boundary_path = workspace_root / BOUNDARY_REPORT
    for path in (long_path, p3_ml_path, p2_report_path, p3_report_path, boundary_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    source_long_rows, source_target_rows = _read_long_panel(long_path)
    execution_window = int(os.environ.get("P4_SUPERTEST_EXECUTION_WINDOW", "90"))
    if execution_window < 16 or execution_window > len(source_long_rows):
        raise ValueError(f"execution window must be between 16 and {len(source_long_rows)}")
    long_rows = source_long_rows[-execution_window:]
    target_rows = source_target_rows[-execution_window:]
    p3_ml_rows = list(csv.DictReader(p3_ml_path.open(newline="", encoding="utf-8")))
    p2_report = json.loads(p2_report_path.read_text(encoding="utf-8"))
    p3_report = json.loads(p3_report_path.read_text(encoding="utf-8"))
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))

    # Keep the contract-complete support lane small; the materialized long
    # panel remains intact at 1,239 rows and supplies the full history.
    inputs, fixture_context = build_full_inputs(periods=90)
    cutoff = datetime.fromisoformat("2026-07-28T23:00:00+00:00")
    context = replace(
        fixture_context,
        as_of_time=cutoff,
        decision_time=cutoff,
        created_at=cutoff + timedelta(minutes=5),
    )
    inputs = _replace_live_inputs(inputs, context, long_rows)
    for artifact in inputs.values():
        if not isinstance(artifact, dict) or "records" not in artifact:
            continue
        artifact["created_at"] = context.created_at.isoformat()
        for field in ("run_id", "cycle_id", "as_of_time", "pipeline_version"):
            if field in artifact:
                artifact[field] = (
                    context.as_of_time.isoformat()
                    if field == "as_of_time"
                    else getattr(context, field)
                )
    p3_handoff = inputs.get("phase4_social_handoff_manifest")
    if isinstance(p3_handoff, dict):
        for entry in p3_handoff.get("entries", []):
            artifact_name = entry.get("artifact_name")
            if artifact_name in inputs and isinstance(inputs[artifact_name], dict):
                source_artifact = inputs[artifact_name]
                entry.update(
                    artifact_id=source_artifact["artifact_id"],
                    row_count=len(source_artifact.get("records", [])),
                    lineage_id=source_artifact["lineage_id"],
                    content_hash=content_hash(source_artifact),
                )
    p4_result = _json(run_integrated_phase(inputs, context, encoder_requested=False, allow_partial=True))
    outputs = {name: _json(value) for name, value in p4_result["outputs"].items()}
    decoder = _decoder_evidence(outputs)

    complete_inputs, complete_context = build_full_inputs(periods=70)
    complete_result = _json(
        run_integrated_phase(
            complete_inputs,
            complete_context,
            encoder_requested=False,
            allow_partial=False,
        )
    )

    artifact_metrics = []
    for name, value in sorted(outputs.items()):
        if not isinstance(value, dict) or "artifact_name" not in value:
            continue
        artifact_metrics.append(
            {
                "artifact_name": name,
                "artifact_id": value.get("artifact_id"),
                "execution_status": value.get("execution_status"),
                "quality_status": value.get("quality_status"),
                "record_count": value.get("record_count", len(value.get("records", []))),
                "lineage_id": value.get("lineage_id"),
            }
        )

    evidence = {
        "schema_version": "P4-V14.9-RC1-P2-P3-SUPERTEST-1",
        "status": "PASS"
        if p4_result["status"] != "BLOCKED"
        and complete_result["status"] != "BLOCKED"
        and decoder["status"] == "PASS"
        else "FAIL",
        "source_mode": "MATERIALIZED_P2_P3_REPORTS_PLUS_P4_CONTRACT_COMPLETE_SUPPORT",
        "scope_note": "The longitudinal panel and P2/P3 reports are repository artifacts. P4 support panels remain the official contract-complete fixture; this is explicit and not promoted as a live provider run.",
        "longitudinal_execution_policy": {
            "source_rows_available": len(source_long_rows),
            "executed_rows": len(long_rows),
            "window": execution_window,
            "policy": "last_causal_window_only",
            "full_history_audit": "SOURCE_INTEGRITY_ONLY",
            "full_history_execution_note": "The complete 1,239-row source spans mixed vintages. Earlier rows do not contain the later P3-enriched feature set, so a global first-fold policy would correctly produce no PCA fit. The executable lane uses the latest causal window and records this limitation instead of treating an empty PCA output as a pass.",
        },
        "target_policy": {
            "source_target_rows": len(source_target_rows),
            "executed_target_audit_rows": len(target_rows),
            "target_passed_to_p4": False,
            "target_audit_only": True,
        },
        "sources": [
            _source_entry(long_path, "P2/P3", len(source_long_rows), target_present=True),
            _source_entry(p3_ml_path, "P3", len(p3_ml_rows)),
            _source_entry(p2_report_path, "P2", 1),
            _source_entry(p3_report_path, "P3", 1),
            _source_entry(boundary_path, "P2→P3", 1),
        ],
        "p2": {
            "report_status": p2_report.get("status"),
            "execution_status": p2_report.get("execution_status"),
            "long_panel_rows": len(source_long_rows),
            "executed_long_panel_rows": len(long_rows),
            "execution_window_policy": "last_90_rows_causal_window",
            "long_panel_start": source_long_rows[0]["date"],
            "long_panel_end": source_long_rows[-1]["date"],
            "indicative_lane_rows": p2_report.get("indicative_lane", {}).get("row_count"),
            "provider_count": len(p2_report.get("providers", [])),
        },
        "p3": {
            "report_status": p3_report.get("status"),
            "ml_panel_rows": len(p3_ml_rows),
            "boundary_status": boundary.get("status"),
            "validation_status": boundary.get("p3_validation_status"),
            "context_records": boundary.get("p2_context_records"),
            "document_records": boundary.get("p2_document_records"),
            "event_records": boundary.get("p2_event_records"),
            "rejected_records": boundary.get("p3_rejected_records"),
        },
        "p4": {
            "status": p4_result["status"],
            "release": p4_result["release"],
            "integration_report": p4_result["integration_report"],
            "artifact_metrics": artifact_metrics,
            "quality_gate_records": outputs.get("p4_quality_gate_decision", {}).get("records", []),
            "handoff_metadata": outputs.get("phase5_feature_handoff_manifest", {}).get("metadata", {}),
            "handoff_records": outputs.get("phase5_feature_handoff_manifest", {}).get("records", []),
            "contract_complete_lane": {
                "status": complete_result["status"],
                "release": complete_result["release"],
                "integration_report": complete_result["integration_report"],
                "artifact_metrics": [
                    {
                        "artifact_name": name,
                        "execution_status": value.get("execution_status"),
                        "quality_status": value.get("quality_status"),
                        "record_count": value.get("record_count", len(value.get("records", []))),
                    }
                    for name, value in sorted(complete_result["outputs"].items())
                    if isinstance(value, dict) and "artifact_name" in value
                ],
            },
        },
        "decoder": decoder,
        "tables": {
            "long_input": [
                {key: value for key, value in row.items() if key not in {"target"}}
                for row in source_long_rows
            ],
            "executed_long_input": long_rows,
            "target_audit": source_target_rows,
            "p3_ml_input": p3_ml_rows,
            "artifact_metrics": artifact_metrics,
            "decoder_check": [decoder],
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "p4_supertest_evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, default=WORKSPACE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    evidence = run(args.workspace_root.resolve(), args.output_dir.resolve())
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "p4_status": evidence["p4"]["status"],
                "p4_contract_complete_status": evidence["p4"]["contract_complete_lane"]["status"],
                "decoder_status": evidence["decoder"]["status"],
            }
        )
    )
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
