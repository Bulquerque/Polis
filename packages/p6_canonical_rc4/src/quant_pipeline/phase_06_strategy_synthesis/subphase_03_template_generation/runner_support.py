"""P6.S3 template planner and family-generation module support."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..domain.enums import CapabilityStatus
from ..domain.models import CapabilityRecord
from ..foundation.artifacts import ArtifactEnvelope, ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .generation import generate_template_family
from .planning import TemplatePlan


def _artifact(
    records: Iterable[Any],
    artifact_type: str,
    module_id: str,
    context: PhaseContext,
    input_ids: Iterable[str] = (),
    status: ArtifactStatus | None = None,
) -> ArtifactEnvelope[Any]:
    return build_artifact(
        artifact_type=artifact_type,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        input_artifact_ids=input_ids,
        status=status,
    )


def parameter_plan(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> ModuleResult:
    """Build the deterministic in-memory template plan and its capability record."""
    module_id = "P6.S3.M07"
    plan = TemplatePlan(
        inputs["eligible_option_contract_panel"].records,
        inputs["eligible_option_quote_panel"].records,
        inputs["validated_underlying_panel"].records,
        inputs["validated_market_belief_state"].records,
        configuration,
    )
    record = CapabilityRecord(
        capability="TEMPLATE_PARAMETER_PLAN",
        status=CapabilityStatus.AVAILABLE,
        reason_code="AVAILABLE",
        planned_wave=1,
    )
    artifact = _artifact((record,), "template_parameter_plan", module_id, context)
    return ModuleResult(
        module_id=module_id,
        outputs={"template_parameter_plan": artifact, "_template_plan": plan},
    )


def family(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
    family_name: str,
    module_id: str,
    output_name: str,
) -> ModuleResult:
    """Generate and publish one template family with traces and rejections."""
    plan = inputs["_template_plan"]
    candidates, traces, rejections = generate_template_family(
        family_name,
        plan,
        configuration,
    )
    candidate_artifact = _artifact(candidates, output_name, module_id, context)
    trace_artifact = _artifact(
        traces,
        f"{output_name}_trace",
        module_id,
        context,
    )
    rejection_status = (
        ArtifactStatus.COMPLETE if rejections else ArtifactStatus.EMPTY_VALID
    )
    rejection_artifact = _artifact(
        rejections,
        f"{output_name}_rejections",
        module_id,
        context,
        status=rejection_status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={
            output_name: candidate_artifact,
            f"{output_name}_trace": trace_artifact,
            f"{output_name}_rejections": rejection_artifact,
        },
    )
