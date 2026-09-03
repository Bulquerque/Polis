from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any

from .canonical import (
    ensure_mapping,
    format_utc,
    parse_aware_datetime,
    require_no_forbidden_fields,
    require_no_secrets,
    stable_sha256,
)
from .errors import Issue, S2ContractError
from .models import ExecutionProfile, S2Settings, ValidationStatus
from .schemas import SchemaRegistry
from .canary import run_canary_suite

LOGGER = logging.getLogger(__name__)


def _log_event(event: str, **fields: Any) -> None:
    LOGGER.info(event, extra={"event": event, **fields})


def _optional_date(value: Any, *, field: str) -> datetime | None:
    if value in (None, "", "UNKNOWN"):
        return None
    text = str(value)
    if len(text) == 10:
        text = f"{text}T00:00:00Z"
    return parse_aware_datetime(text, field=field)


def _models(registry: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    top_models = registry.get("models")
    if isinstance(top_models, list):
        for model in top_models:
            if isinstance(model, dict):
                result.append(dict(model))
    providers = registry.get("providers")
    if isinstance(providers, list):
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            for model in provider.get("models", []):
                if not isinstance(model, dict):
                    continue
                result.append(
                    {
                        "provider_id": provider.get("provider_id"),
                        "adapter_id": provider.get("adapter_id"),
                        "adapter_version": provider.get("adapter_version"),
                        **model,
                    }
                )
    return sorted(
        result,
        key=lambda model: (
            str(model.get("provider_id", "")),
            str(model.get("model_id", "")),
            str(model.get("model_version", "")),
        ),
    )


def _classify_model(
    model: dict[str, Any],
    *,
    as_of: datetime,
    profile: ExecutionProfile,
    policy: dict[str, Any],
) -> dict[str, Any]:
    provider_id = str(model.get("provider_id", "UNKNOWN"))
    model_id = str(model.get("model_id", ""))
    model_version = str(model.get("model_version", model.get("revision", "")))
    release_date = _optional_date(model.get("release_date"), field="release_date")
    declared_cutoff = _optional_date(
        model.get("declared_knowledge_cutoff", model.get("knowledge_cutoff")),
        field="declared_knowledge_cutoff",
    )
    training_cutoff = _optional_date(
        model.get("training_data_cutoff", model.get("training_cutoff")),
        field="training_data_cutoff",
    )
    canary = str(model.get("canary_test_status", "NOT_RUN")).upper()
    evidence_refs = [str(item) for item in model.get("evidence_refs", [])]
    rationale: list[str] = []

    if canary in {"DETECTED", "FAILED", "FAIL", "CONTAMINATION_DETECTED"}:
        risk = "CANARY_CONTAMINATION_DETECTED"
        disposition = "BLOCKED"
        rationale.append("A contamination canary detected future-knowledge risk.")
    elif training_cutoff is not None and training_cutoff > as_of:
        risk = "TRAINING_CUTOFF_AFTER_AS_OF"
        disposition = "BLOCKED_FOR_QUALIFICATION"
        rationale.append("Training data cutoff is after the run as_of boundary.")
    elif declared_cutoff is not None and declared_cutoff > as_of:
        risk = "KNOWLEDGE_CUTOFF_AFTER_AS_OF"
        disposition = "BLOCKED_FOR_QUALIFICATION"
        rationale.append("Declared knowledge cutoff is after the run as_of boundary.")
    elif release_date is not None and release_date > as_of:
        risk = "RELEASE_AFTER_AS_OF"
        disposition = "BLOCKED_FOR_QUALIFICATION"
        rationale.append("Model release date is after the historical run boundary.")
    elif not model_id or not model_version:
        risk = "UNQUALIFIED_METADATA"
        disposition = "BLOCKED_FOR_QUALIFICATION"
        rationale.append("Model identity or version metadata is incomplete.")
    elif release_date is None or (declared_cutoff is None and training_cutoff is None):
        risk = "UNKNOWN_CUTOFF"
        disposition = "BLOCKED_FOR_QUALIFICATION"
        rationale.append("Knowledge/training cutoff metadata is incomplete or unknown.")
    else:
        risk = "LOWER_RISK_KNOWN_PRE_AS_OF"
        disposition = "ALLOWED_WITH_DISCLOSURE"
        rationale.append(
            "Known release and cutoff metadata do not extend beyond as_of; "
            "this lowers risk but does not prove absence of memorized future knowledge."
        )

    if risk == "CANARY_CONTAMINATION_DETECTED":
        raise S2ContractError(
            "P3_S2_M03_CANARY_CONTAMINATION_DETECTED",
            f"Contamination canary blocked {provider_id}/{model_id or 'UNKNOWN'}",
        )
    if profile is ExecutionProfile.DEVELOPMENT and disposition == "BLOCKED_FOR_QUALIFICATION":
        disposition = "ALLOWED_FOR_DEVELOPMENT"
    if profile is ExecutionProfile.QUALIFICATION and risk in {
        "UNKNOWN_CUTOFF",
        "UNQUALIFIED_METADATA",
    } and str(policy.get("qualification_unknown_action", "fail_closed")) != "fail_closed":
        raise S2ContractError(
            "P3_S2_M03_POLICY_NOT_FAIL_CLOSED",
            "Qualification policy for unknown cutoff must be fail_closed",
        )
    return {
        "provider_id": provider_id,
        "model_id": model_id or "UNKNOWN",
        "model_version": model_version or "UNKNOWN",
        "adapter_id": str(model.get("adapter_id", "UNKNOWN")),
        "adapter_version": str(model.get("adapter_version", "UNKNOWN")),
        "release_date": format_utc(release_date),
        "declared_knowledge_cutoff": format_utc(declared_cutoff),
        "training_data_cutoff": format_utc(training_cutoff),
        "canary_test_status": canary,
        "risk_class": risk,
        "qualification_disposition": disposition,
        "rationale": " ".join(rationale),
        "evidence_refs": sorted(evidence_refs),
    }


def _validated_cutoff_inputs(
    inputs: dict[str, Any],
    registry: SchemaRegistry,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    required = (
        "phase3_run_snapshot",
        "provider_adapter_registry_config",
        "evaluation_protocol_config",
        "model_knowledge_cutoff_policy_config",
    )
    missing = [name for name in required if name not in inputs]
    if missing:
        raise S2ContractError(
            "P3_S2_M03_REQUIRED_INPUT_MISSING",
            f"Missing inputs: {missing}",
        )
    snapshot = ensure_mapping(inputs[required[0]], required[0])
    providers = ensure_mapping(inputs[required[1]], required[1])
    protocol = ensure_mapping(inputs[required[2]], required[2])
    policy = ensure_mapping(inputs[required[3]], required[3])
    registry.validate_internal("phase3_run_snapshot", snapshot)
    for name, value in zip(required, (snapshot, providers, protocol, policy), strict=True):
        require_no_forbidden_fields(value, name)
        require_no_secrets(value, name)
    return snapshot, providers, protocol, policy


def _validate_cutoff_policy(policy: dict[str, Any]) -> None:
    if bool(policy.get("post_cutoff_preferred", False)):
        raise S2ContractError(
            "P3_S2_M03_POST_CUTOFF_POLICY_INVERTED",
            "post_cutoff_preferred must be false for historical evaluation",
        )
    if not bool(policy.get("never_claim_clean_when_unknown", True)):
        raise S2ContractError(
            "P3_S2_M03_UNKNOWN_MAY_NOT_BE_CLEAN",
            "Unknown cutoff may never be classified as clean",
        )


def _empty_inventory_result(
    *,
    settings: S2Settings,
) -> tuple[list[dict[str, Any]], list[Issue], str, str]:
    issues = [
        Issue(
            code="P3_S2_M03_NO_MODELS_DECLARED",
            severity="ERROR",
            message="No concrete model inventory is declared",
            artifact_name="provider_adapter_registry_config",
        )
    ]
    if (
        settings.execution_profile is ExecutionProfile.QUALIFICATION
        and settings.require_concrete_model_inventory_in_qualification
    ):
        raise S2ContractError(
            "P3_S2_M03_NO_MODELS_DECLARED",
            "Qualification requires a concrete model inventory",
            issues=issues,
        )
    return [], issues, "NO_MODELS_DECLARED", "ALLOWED_FOR_DEVELOPMENT"


def _aggregate_model_risk(classified: list[dict[str, Any]]) -> tuple[str, str]:
    risk_priority = {
        "CANARY_CONTAMINATION_DETECTED": 7,
        "TRAINING_CUTOFF_AFTER_AS_OF": 6,
        "KNOWLEDGE_CUTOFF_AFTER_AS_OF": 5,
        "RELEASE_AFTER_AS_OF": 4,
        "UNQUALIFIED_METADATA": 3,
        "UNKNOWN_CUTOFF": 2,
        "LOWER_RISK_KNOWN_PRE_AS_OF": 1,
    }
    disposition_priority = {
        "BLOCKED": 4,
        "BLOCKED_FOR_QUALIFICATION": 3,
        "ALLOWED_FOR_DEVELOPMENT": 2,
        "ALLOWED_WITH_DISCLOSURE": 1,
    }
    overall_risk = max(
        (row["risk_class"] for row in classified),
        key=risk_priority.__getitem__,
    )
    overall_disposition = max(
        (row["qualification_disposition"] for row in classified),
        key=disposition_priority.__getitem__,
    )
    return overall_risk, overall_disposition


def _classify_inventory(
    *,
    providers: dict[str, Any],
    snapshot: dict[str, Any],
    settings: S2Settings,
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Issue], str, str]:
    model_rows = _models(providers)
    if not model_rows:
        return _empty_inventory_result(settings=settings)
    as_of = parse_aware_datetime(snapshot["temporal"]["as_of"], field="snapshot.as_of")
    classified = [
        _classify_model(
            model,
            as_of=as_of,
            profile=settings.execution_profile,
            policy=policy,
        )
        for model in model_rows
    ]
    overall_risk, overall_disposition = _aggregate_model_risk(classified)
    if (
        settings.execution_profile is ExecutionProfile.QUALIFICATION
        and overall_disposition in {"BLOCKED", "BLOCKED_FOR_QUALIFICATION"}
    ):
        raise S2ContractError(
            "P3_S2_M03_QUALIFICATION_BLOCKED",
            f"Model knowledge risk blocks qualification: {overall_risk}",
        )
    return classified, [], overall_risk, overall_disposition


def _build_cutoff_report(
    *,
    snapshot: dict[str, Any],
    protocol: dict[str, Any],
    policy: dict[str, Any],
    classified: list[dict[str, Any]],
    issues: list[Issue],
    overall_risk: str,
    overall_disposition: str,
) -> dict[str, Any]:
    status = (
        ValidationStatus.READY
        if not issues and overall_disposition == "ALLOWED_WITH_DISCLOSURE"
        else ValidationStatus.DEGRADED
    )
    output: dict[str, Any] = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s2.model_knowledge_cutoff_report.v2",
        "validation_status": status.value,
        "snapshot_id": str(snapshot["identity"]["snapshot_id"]),
        "evaluation_window": {
            "as_of": str(snapshot["temporal"]["as_of"]),
            "evaluation_start": snapshot["temporal"].get("evaluation_start"),
            "evaluation_end": snapshot["temporal"].get("evaluation_end"),
            "final_holdout_blind": bool(protocol.get("final_holdout_blind", True)),
        },
        "policy": {
            "version": str(policy.get("version", "unknown")),
            "post_cutoff_preferred": False,
            "never_claim_clean_when_unknown": True,
            "qualification_unknown_action": str(
                policy.get("qualification_unknown_action", "fail_closed")
            ),
        },
        "models": classified,
        "overall_risk": overall_risk,
        "overall_disposition": overall_disposition,
        "absolute_cleanliness_claimed": False,
        "issues": [issue.to_dict() for issue in issues],
        "lineage_id": f"lineage-p3-s2-cutoff-{stable_sha256(classified)[:20]}",
    }
    output["content_hash"] = stable_sha256(output)
    return output



def _apply_executable_canaries(providers: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    probe=config.get("canary_probe"); suite=config.get("knowledge_canary_suite")
    if probe is None or suite is None: return providers, []
    copied=deepcopy(providers); evidence=[]
    for provider in copied.get("providers",[]):
        for model in provider.get("models",[]):
            result=run_canary_suite(str(provider.get("provider_id")),str(model.get("model_id")),suite,probe)
            model["canary_test_status"]=result["status"]
            model["canary_evidence_ref"]="canary:"+result["suite_hash"]
            evidence.append({"provider_id":provider.get("provider_id"),"model_id":model.get("model_id"),**result})
    return copied,evidence

def classify_model_knowledge_cutoff(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify model knowledge risk without claiming absolute cleanliness."""

    config = config or {}
    settings = S2Settings.from_mapping(config)
    registry = SchemaRegistry()
    immutable_copy = deepcopy(inputs)
    _log_event("module_started", module_id="P3.S2.M03")

    snapshot, providers, protocol, policy = _validated_cutoff_inputs(inputs, registry)
    providers, canary_evidence = _apply_executable_canaries(providers, config)
    _validate_cutoff_policy(policy)
    classified, issues, overall_risk, overall_disposition = _classify_inventory(
        providers=providers,
        snapshot=snapshot,
        settings=settings,
        policy=policy,
    )
    output = _build_cutoff_report(
        snapshot=snapshot,
        protocol=protocol,
        policy=policy,
        classified=classified,
        issues=issues,
        overall_risk=overall_risk,
        overall_disposition=overall_disposition,
    )
    output["canary_evidence"] = canary_evidence
    output["content_hash"] = stable_sha256({k:v for k,v in output.items() if k != "content_hash"})
    if inputs != immutable_copy:
        raise S2ContractError(
            "P3_S2_INPUT_MUTATION_DETECTED",
            "P3.S2.M03 mutated its inputs",
        )
    registry.validate_internal("model_knowledge_cutoff_report", output)
    require_no_forbidden_fields(output, "model_knowledge_cutoff_report")
    _log_event(
        "module_succeeded",
        module_id="P3.S2.M03",
        validation_status=output["validation_status"],
        model_count=len(classified),
        overall_risk=overall_risk,
        overall_disposition=overall_disposition,
        warning_count=len(issues),
    )
    return output
