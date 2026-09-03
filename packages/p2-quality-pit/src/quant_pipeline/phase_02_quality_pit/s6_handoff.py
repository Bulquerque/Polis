from __future__ import annotations

from typing import Any

from .modules._module_executor import ContractValidationError, _stable_digest


TARGET_ARTIFACTS = {
    "phase_03_agents_rag_memory": (
        "clean_context_source_panel",
        "clean_document_panel",
        "clean_event_reference_panel",
        "source_quality_panel",
    ),
    "phase_04_feature_base": (
        "clean_underlying_panel",
        "clean_macro_br_panel",
        "clean_macro_us_panel",
        "clean_benchmark_panel",
        "clean_calendar_panel",
        "clean_corporate_actions_panel",
        "quality_report_phase_2",
    ),
    "phase_06_candidate_generation": (
        "clean_option_quotes_panel",
        "clean_option_contract_panel",
        "clean_underlying_trade_panel",
        "clean_calendar_panel",
        "clean_cost_reference_panel",
        "clean_liquidity_reference_panel",
    ),
}


def validate_materialized_artifacts(inputs: dict, required: list[str]) -> dict[str, dict]:
    artifacts: dict[str, dict] = {}
    seen_ids: dict[str, str] = {}
    for name in required:
        value = inputs[name]
        if not isinstance(value, dict):
            raise ContractValidationError(f"{name} must be a materialized artifact dict")
        if value.get("source"):
            raise ContractValidationError("handoff inputs cannot be synthesized from source")
        artifact_id = value.get("artifact_id")
        if not artifact_id:
            raise ContractValidationError("handoff_manifest_references_existing_artifacts violation")
        artifact_id = str(artifact_id)
        previous = seen_ids.get(artifact_id)
        if previous is not None and previous != name:
            raise ContractValidationError(
                f"duplicate artifact_id {artifact_id!r} used by {previous!r} and {name!r}"
            )
        seen_ids[artifact_id] = name
        artifacts[name] = value
    return artifacts


def validate_quality_gate(report: dict, config: dict) -> tuple[str, dict]:
    status = str(report.get("status") or "LEGACY_UNVERIFIED").upper()
    readiness = report.get("target_readiness") if isinstance(report.get("target_readiness"), dict) else {}

    if status == "BLOCK":
        raise ContractValidationError("quality_report_phase_2 BLOCK prevents handoff")
    if status == "DEGRADED" and not config.get("allow_degraded_handoffs", False):
        raise ContractValidationError("quality_report_phase_2 DEGRADED requires explicit allow_degraded_handoffs")
    if status not in {"PASS", "WARN", "DEGRADED", "LEGACY_UNVERIFIED"}:
        raise ContractValidationError(f"unsupported quality_report_phase_2 status: {status}")
    if status == "LEGACY_UNVERIFIED" and not config.get("allow_legacy_unverified", True):
        raise ContractValidationError("LEGACY_UNVERIFIED handoff is disabled by the active execution profile")

    strict_target_readiness = bool(config.get("strict_target_readiness", False))

    for target, details in readiness.items():
        if target not in TARGET_ARTIFACTS or not isinstance(details, dict):
            continue
        target_status = str(details.get("status") or "PASS").upper()
        if target_status == "BLOCK" and strict_target_readiness:
            raise ContractValidationError(f"target readiness BLOCK prevents handoff to {target}")
        if target_status == "DEGRADED" and strict_target_readiness and not config.get("allow_degraded_handoffs", False):
            raise ContractValidationError(f"target readiness DEGRADED prevents handoff to {target}")
    return status, readiness


def artifact_ref(name: str, artifact: dict) -> dict:
    return {
        "artifact_name": name,
        "artifact_id": str(artifact["artifact_id"]),
        "schema_version": artifact.get("schema_version"),
        "content_hash": artifact.get("content_hash") or _stable_digest(artifact),
        "lineage_id": artifact.get("lineage_id"),
    }


def build_target_payload(target: str, artifacts: dict[str, dict], quality_status: str) -> dict:
    names = TARGET_ARTIFACTS[target]
    refs = [artifact_ref(name, artifacts[name]) for name in names]
    return {
        "target_phase": target,
        "target_artifact_ids": [ref["artifact_id"] for ref in refs],
        "artifact_refs": refs,
        "quality_status": quality_status,
    }


def handoff_identity(target_payload: dict, pipeline_version: str) -> str:
    identity_payload = {
        "target_phase": target_payload["target_phase"],
        "target_artifact_ids": target_payload["target_artifact_ids"],
        "artifact_hashes": [ref["content_hash"] for ref in target_payload["artifact_refs"]],
        "pipeline_version": pipeline_version,
    }
    return _stable_digest(identity_payload)


def lineage_for_target(target_payload: dict) -> str:
    lineage_values = [ref.get("lineage_id") or ref["artifact_id"] for ref in target_payload["artifact_refs"]]
    return f"lineage-handoff-{_stable_digest(lineage_values)[:20]}"


def assert_no_hidden_bundle(manifest: dict) -> None:
    forbidden_payload_keys = {"records", "rows", "items", "sources", "snapshots", "documents", "quotes"}

    def walk(value: Any, path: str = "manifest") -> None:
        if isinstance(value, dict):
            leaked = forbidden_payload_keys.intersection(value)
            if leaked:
                raise ContractValidationError(
                    f"hidden bundle payload detected at {path}: {sorted(leaked)}"
                )
            for key, item in value.items():
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(manifest)
