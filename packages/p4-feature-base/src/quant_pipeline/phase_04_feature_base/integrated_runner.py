from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from typing import Any

import yaml

from .adapters import (
    build_representation_policy,
    build_research_attempt_event_log,
    build_s7_policy_artifacts,
    build_s9_policy,
    canonical_panel_for_economic,
    compile_atomic_execution_registry,
    economic_hypothesis_registry,
    horizon_panel_for_s7,
)
from .models import ExecutionContext as FoundationContext
from .runner import run_foundation_and_governance
from .runner_s4 import run_subphase_s4
from .runner_s5 import run_subphase_s5
from .runner_s6 import run_subphase_s6
from .runtime.artifact_envelope import RuntimeExecutionContext
from .s7.runner import run_subphase as run_s7
from .s8.runner import run_subphase as run_s8
from .s9.runner import run_subphase as run_s9


@dataclass(frozen=True, slots=True)
class IntegratedRunResult:
    phase_id: str
    release: str
    status: str
    subphases: Mapping[str, Any]
    outputs: Mapping[str, Any]
    integration_report: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "release": self.release,
            "status": self.status,
            "subphases": dict(self.subphases),
            "outputs": dict(self.outputs),
            "integration_report": dict(self.integration_report),
        }


def _runtime_context(context: FoundationContext) -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        created_at=context.created_at,
        pipeline_version=context.pipeline_version,
    )


def _economic_config(context: FoundationContext) -> dict[str, Any]:
    return {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time,
        "created_at": context.created_at,
        "pipeline_version": context.pipeline_version,
    }


def _load_bound_registry(name: str, context: FoundationContext) -> dict[str, Any]:
    resource = files("quant_pipeline.phase_04_feature_base._resources.registries_economic").joinpath(name)
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    data["pipeline_version"] = context.pipeline_version
    data["run_id"] = context.run_id
    data["cycle_id"] = context.cycle_id
    data["as_of_time"] = context.as_of_time.isoformat()
    data["lineage_id"] = f"lineage:{name}:{context.run_id}:{context.cycle_id}"
    return data


def _economic_authorities(
    foundation_outputs: Mapping[str, Any], context: FoundationContext
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    hypotheses = foundation_outputs["approved_hypothesis_passport_registry"]
    shared = {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": context.as_of_time,
        "pipeline_version": context.pipeline_version,
    }
    panel = canonical_panel_for_economic(
        foundation_outputs["canonical_observation_panel"],
        created_at=context.created_at,
        **{key: shared[key] for key in ("run_id", "cycle_id", "as_of_time")},
    )
    return (
        panel,
        compile_atomic_execution_registry(hypotheses, **shared),
        economic_hypothesis_registry(hypotheses, **shared),
    )


def _fusion_registries(context: FoundationContext) -> dict[str, dict[str, Any]]:
    names = {
        "alignment_policy_registry": "DEFAULT_ALIGNMENT_POLICY_REGISTRY.yaml",
        "conflict_group_registry": "DEFAULT_CONFLICT_GROUP_REGISTRY.yaml",
        "approved_interaction_registry": "DEFAULT_APPROVED_INTERACTION_REGISTRY.yaml",
    }
    return {key: _load_bound_registry(filename, context) for key, filename in names.items()}


def run_foundation_to_fusion(
    inputs: Mapping[str, Any], context: FoundationContext
) -> dict[str, Any]:
    """Execute S1-S6 with both cross-contract boundaries reconciled."""
    foundation = run_foundation_and_governance(inputs, context)
    foundation_outputs = foundation["outputs"]
    economic_panel, atomic_registry, economic_registry = _economic_authorities(
        foundation_outputs, context
    )
    config = _economic_config(context)
    s4 = run_subphase_s4(
        {
            "canonical_observation_panel": economic_panel,
            "approved_observer_execution_registry": atomic_registry,
        },
        config,
    )
    s5 = run_subphase_s5(
        {**s4["outputs"], "approved_hypothesis_passport_registry": economic_registry},
        config,
    )
    s6 = run_subphase_s6(
        {
            **s5["outputs"],
            "approved_hypothesis_passport_registry": economic_registry,
            **_fusion_registries(context),
        },
        config,
    )
    return {
        "subphases": {
            **foundation["subphases"],
            "P4.S4": s4,
            "P4.S5": s5,
            "P4.S6": s6,
        },
        "outputs": {
            **foundation_outputs,
            **s4["outputs"],
            **s5["outputs"],
            **s6["outputs"],
        },
        "boundary_artifacts": {
            "economic_canonical_observation_panel": economic_panel,
            "atomic_execution_registry": atomic_registry,
            "economic_hypothesis_registry": economic_registry,
        },
    }


def run_transform_to_assurance(
    horizon_panel: Mapping[str, Any],
    context: FoundationContext,
    *,
    encoder_requested: bool = False,
    allow_partial_handoff: bool = False,
    s9_policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute S7-S9 from an actual S6 horizon feature panel."""
    runtime_context = _runtime_context(context)
    horizon = horizon_panel_for_s7(horizon_panel, context=runtime_context)
    s7_policies = build_s7_policy_artifacts(horizon, context=runtime_context)
    s7 = run_s7({"horizon_feature_panel": horizon, **s7_policies}, runtime_context)
    representation_policy = build_representation_policy(
        context=runtime_context, encoder_requested=encoder_requested
    )
    s8 = run_s8({**s7, "representation_policy_registry": representation_policy}, runtime_context)
    s9_policy = build_s9_policy(
        context=runtime_context,
        strict_complete_handoff=not allow_partial_handoff,
        overrides=s9_policy_overrides,
    )
    event_log = build_research_attempt_event_log(context=runtime_context)
    s9 = run_s9(
        {
            **s7,
            **s8,
            "s9_policy_registry": s9_policy,
            "research_attempt_event_log": event_log,
        },
        runtime_context,
    )
    return {
        "subphases": {"P4.S7": s7, "P4.S8": s8, "P4.S9": s9},
        "outputs": {**s7, **s8, **s9},
        "boundary_artifacts": {
            "horizon_feature_panel": horizon,
            **s7_policies,
            "representation_policy_registry": representation_policy,
            "s9_policy_registry": s9_policy,
            "research_attempt_event_log": event_log,
        },
    }


def _integration_report(horizon: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    records = [record for record in horizon.get("records", []) if isinstance(record, Mapping)]
    timestamps = {str(record.get("decision_time")) for record in records}
    features = {
        str(record.get("feature_id"))
        for record in records
        if record.get("value") is not None
    }
    report = {
        "a1_to_a2_adapter": "PASS",
        "a2_to_a3_adapter": "NOT_RUN",
        "horizon_timestamp_count": len(timestamps),
        "observed_feature_count": len(features),
        "minimum_downstream_timestamps": 16,
        "minimum_downstream_features": 2,
    }
    ready = len(timestamps) >= 16 and len(features) >= 2
    return report, ready


def _partial_result(
    upstream: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    return IntegratedRunResult(
        phase_id="P4",
        release="V14.9-RC1",
        status="DEGRADED_INSUFFICIENT_HISTORY",
        subphases=upstream["subphases"],
        outputs=upstream["outputs"],
        integration_report=report,
    ).to_dict()


def _status_from_handoff(handoff: Any) -> str:
    handoff_status = str(handoff.execution_status)
    completeness = str(handoff.metadata.get("completeness_status") or "UNKNOWN")
    if handoff_status == "BLOCKED":
        return "BLOCKED"
    if handoff_status == "DEGRADED" and completeness == "PARTIAL":
        return "DEGRADED_PARTIAL_HANDOFF"
    if handoff_status == "DEGRADED":
        return "DEGRADED_QUALITY"
    return "PRODUCED"


def run_integrated_phase(
    inputs: Mapping[str, Any],
    context: FoundationContext,
    *,
    encoder_requested: bool = False,
    allow_partial: bool = True,
    s9_policy_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run P4 S1-S9, returning a controlled partial result when needed."""
    upstream = run_foundation_to_fusion(inputs, context)
    horizon = upstream["outputs"]["horizon_feature_panel"]
    report, ready = _integration_report(horizon)
    if not ready:
        if allow_partial:
            return _partial_result(upstream, report)
        raise ValueError(
            "insufficient S6 history for S7-S9: "
            f"timestamps={report['horizon_timestamp_count']} "
            f"features={report['observed_feature_count']}"
        )
    downstream = run_transform_to_assurance(
        horizon,
        context,
        encoder_requested=encoder_requested,
        allow_partial_handoff=allow_partial,
        s9_policy_overrides=s9_policy_overrides,
    )
    report["a2_to_a3_adapter"] = "PASS"
    handoff = downstream["outputs"]["phase5_feature_handoff_manifest"]
    report["handoff_completeness_status"] = handoff.metadata.get("completeness_status")
    report["handoff_gate_decision"] = handoff.metadata.get("gate_decision")
    return IntegratedRunResult(
        phase_id="P4",
        release="V14.9-RC1",
        status=_status_from_handoff(handoff),
        subphases={**upstream["subphases"], **downstream["subphases"]},
        outputs={**upstream["outputs"], **downstream["outputs"]},
        integration_report=report,
    ).to_dict()
