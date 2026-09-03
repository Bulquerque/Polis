"""Native P6 RC6.1 boundary adapter for the canonical P7 S1 contract."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..canonical import content_sha256
from ..models import ArtifactEnvelope, ModuleConfig
from .p6_native_validation import NativeP6Bundle, P7_OPTIONAL, P7_REQUIRED, validate_native_bundle
from .p6_record_normalization import normalize_artifact_records

ADAPTER_ID = "P7.S1.P6_NATIVE_ADAPTER"
ADAPTER_CONTRACT_VERSION = "2.3.0"
GRAINS = {
    "strategy_candidate_panel": "one_record_per_candidate",
    "strategy_leg_panel": "one_record_per_candidate_leg",
    "strategy_market_snapshot": "one_record_per_market_snapshot",
    "strategy_payoff_panel": "one_record_per_candidate",
    "strategy_scenario_evaluation_panel": "one_record_per_candidate_scenario",
    "strategy_ambiguity_evaluation_panel": "one_record_per_candidate_ambiguity_case",
    "strategy_greek_panel": "one_record_per_candidate",
    "strategy_risk_panel": "one_record_per_candidate",
    "strategy_cost_liquidity_panel": "one_record_per_candidate",
    "strategy_lineage_panel": "one_record_per_candidate",
    "strategy_generation_trace_panel": "one_record_per_candidate",
    "candidate_equivalence_panel": "one_record_per_candidate",
    "candidate_rejection_report": "one_record_per_rejection",
    "candidate_generation_audit": "one_record_per_generation_run",
    "candidate_feature_base_panel": "one_record_per_candidate",
}


@dataclass(frozen=True, slots=True)
class NativeP6Adaptation:
    manifest: dict[str, Any]
    artifacts: list[dict[str, Any]]
    module_config: dict[str, Any]
    compatibility_report: dict[str, Any]


def adapt_native_p6_handoff(
    manifest_payload: Mapping[str, Any], artifact_payloads: Sequence[Mapping[str, Any]],
    module_config_payload: Mapping[str, Any],
) -> NativeP6Adaptation:
    native = validate_native_bundle(manifest_payload, artifact_payloads)
    source_record = native.manifest_record
    effective_config = _effective_config(module_config_payload, native)
    config = ModuleConfig.model_validate(effective_config)
    candidate_ids = frozenset(
        str(row["candidate_id"]) for row in native.artifacts["strategy_candidate_panel"]["records"]
    )
    snapshot_id = _snapshot_id(native)
    selected_names = list(P7_REQUIRED)
    selected_names.extend(name for name in P7_OPTIONAL if name in native.artifacts and name in GRAINS)
    normalized: list[dict[str, Any]] = []
    for name in selected_names:
        source = native.artifacts[name]
        records = normalize_artifact_records(
            name, list(source["records"]), cycle_id=str(source_record["cycle_id"]),
            decision_time=str(source_record["decision_time"]), market_snapshot_id=snapshot_id,
            published_candidate_ids=candidate_ids, artifacts=native.artifacts,
        )
        normalized.append(_external_artifact(name, records, source, config, native))
    manifest = _normalized_manifest(normalized, native, config)
    report = _compatibility_report(native, normalized, snapshot_id)
    return NativeP6Adaptation(manifest, normalized, effective_config, report)


def _effective_config(payload: Mapping[str, Any], native: NativeP6Bundle) -> dict[str, Any]:
    config = dict(payload)
    context = dict(config.get("context", {}))
    manifest = native.manifest_envelope
    record = native.manifest_record
    context.update({
        "run_id": str(manifest["run_id"]),
        "cycle_id": str(record["cycle_id"]),
        "decision_time": str(record["decision_time"]),
        "available_at": str(record["decision_time"]),
        "lineage_id": f"p6-native:{manifest['lineage_id']}",
    })
    config["context"] = context
    return config


def _snapshot_id(native: NativeP6Bundle) -> str:
    records = native.artifacts["strategy_market_snapshot"]["records"]
    if len(records) != 1:
        raise ValueError("native P6 strategy_market_snapshot must contain one record")
    snapshot_id = records[0].get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("native P6 strategy market snapshot has no snapshot_id")
    return snapshot_id


def _external_artifact(
    name: str, records: list[dict[str, Any]], source: Mapping[str, Any],
    config: ModuleConfig, native: NativeP6Bundle,
) -> dict[str, Any]:
    source_status = str(source.get("status", "COMPLETE"))
    if source_status in {"BLOCKED", "ERROR"}:
        capability = "UNAVAILABLE"
    elif source_status == "DEGRADED":
        capability = "DEGRADED"
    else:
        capability = "AVAILABLE" if records else "UNAVAILABLE"
    base = {
        "artifact_id": "pending",
        "artifact_name": name,
        "schema_version": ADAPTER_CONTRACT_VERSION,
        "producer_phase": "P6",
        "producer_module_id": ADAPTER_ID,
        "destination_phase": "P7",
        "pipeline_version": config.context.pipeline_version,
        "run_id": config.context.run_id,
        "cycle_id": config.context.cycle_id,
        "decision_time": config.context.decision_time,
        "available_at": config.context.decision_time,
        "created_at": config.context.created_at,
        "record_count": len(records),
        "grain": GRAINS[name],
        "lineage_id": f"p6-source:{source['lineage_id']}",
        "capability_status": capability,
        "records": records,
    }
    identity_hash = content_sha256({
        "source_artifact_id": source["artifact_id"], "source_hash": source["content_sha256"],
        "adapter_contract": ADAPTER_CONTRACT_VERSION, "records": records,
    })
    base["artifact_id"] = f"p6-p7-{name}-{identity_hash[:24]}"
    placeholder = ArtifactEnvelope.model_validate({**base, "content_sha256": "0" * 64})
    payload = placeholder.hash_payload()
    return ArtifactEnvelope.model_validate({**payload, "content_sha256": content_sha256(payload)}).model_dump(mode="json")


def _normalized_manifest(
    artifacts: list[dict[str, Any]], native: NativeP6Bundle, config: ModuleConfig,
) -> dict[str, Any]:
    references = [{
        "artifact_name": artifact["artifact_name"], "artifact_id": artifact["artifact_id"],
        "content_sha256": artifact["content_sha256"], "schema_version": artifact["schema_version"],
        "record_count": artifact["record_count"], "required": artifact["artifact_name"] in P7_REQUIRED,
        "grain": artifact["grain"],
    } for artifact in artifacts]
    return {
        "manifest_id": f"p6-p7-handoff-{content_sha256(references)[:24]}",
        "contract_version": ADAPTER_CONTRACT_VERSION,
        "schema_version": ADAPTER_CONTRACT_VERSION,
        "producer_phase": "P6", "destination_phase": "P7",
        "pipeline_version": config.context.pipeline_version,
        "run_id": config.context.run_id, "cycle_id": config.context.cycle_id,
        "decision_time": config.context.decision_time.isoformat(),
        "created_at": config.context.created_at.isoformat(),
        "artifacts": references,
    }


def _compatibility_report(
    native: NativeP6Bundle, normalized: list[dict[str, Any]], snapshot_id: str,
) -> dict[str, Any]:
    p5_report = native.artifacts.get("p5_handoff_compatibility_report", {}).get("records", [])
    p5_record = p5_report[0] if len(p5_report) == 1 else None
    snapshot_rows = native.artifacts["strategy_market_snapshot"]["records"]
    snapshot = snapshot_rows[0] if len(snapshot_rows) == 1 else {}
    p5_manifest_id = (p5_record.get("manifest_id") if isinstance(p5_record, Mapping)
                      else snapshot.get("p5_manifest_id"))
    p5_manifest_hash = (p5_record.get("manifest_sha256") if isinstance(p5_record, Mapping)
                        else snapshot.get("p5_manifest_sha256"))
    source_ids = snapshot.get("p5_source_artifact_ids", []) if isinstance(snapshot, Mapping) else []
    inferred_p5_status = "COMPLETE" if source_ids else ("DEGRADED" if p5_manifest_id else "UNAVAILABLE")
    return {
        "status": "PASS",
        "adapter_contract_version": ADAPTER_CONTRACT_VERSION,
        "source_p6_schema_version": native.manifest_envelope["schema_version"],
        "source_p6_pipeline_version": native.manifest_envelope.get("metadata", {}).get("pipeline_version"),
        "source_manifest_id": native.manifest_record["handoff_id"],
        "source_manifest_artifact_id": native.manifest_envelope["artifact_id"],
        "source_manifest_content_sha256": native.manifest_envelope["content_sha256"],
        "normalized_artifact_count": len(normalized),
        "ignored_native_artifacts": list(native.ignored_artifact_names),
        "market_snapshot_id": snapshot_id,
        "clock_normalization_basis": "P6_VALIDATED_DECISION_ANCHOR",
        "p5_provenance_status": p5_record.get("validation_status") if isinstance(p5_record, Mapping) else inferred_p5_status,
        "p5_manifest_id": p5_manifest_id,
        "p5_manifest_sha256": p5_manifest_hash,
        "p5_full_manifest_consumed": p5_record.get("full_manifest_consumed") if isinstance(p5_record, Mapping) else bool(source_ids),
        "p5_source_artifact_count": len(source_ids),
    }
