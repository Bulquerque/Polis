from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..domain.errors import fail
from ..subphases.s6_runtime_scoring.compatibility import resolve_runtime_model, validate_tournament_candidate_sets, validate_tournament_handoff
from ..subphases.s6_runtime_scoring.contracts import CandidateFeatureRecord, RuntimePolicy, REQUIRED_TOURNAMENT_ARTIFACTS

MODULE_ID = "P7.S6.M01"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    manifest = parse_artifact(inputs.get("interpretable_tournament_handoff_manifest"), name="interpretable_tournament_handoff_manifest")
    tournament = {name: parse_artifact(inputs.get(name), name=name) for name in REQUIRED_TOURNAMENT_ARTIFACTS}
    validate_tournament_handoff(manifest.records, tournament)
    validate_tournament_candidate_sets(tournament, context.decision_time)
    candidates = tuple(CandidateFeatureRecord.model_validate(row).model_dump(mode="json") for row in tournament["factor_adjusted_candidate_panel"].records)
    models = parse_artifact(inputs.get("ltr_model_artifact"), name="ltr_model_artifact")
    qualification = parse_artifact(inputs.get("ltr_model_qualification_registry"), name="ltr_model_qualification_registry")
    governance = parse_artifact(inputs.get("governed_model_registry"), name="governed_model_registry")
    for artifact in (manifest, *tournament.values(), models, qualification, governance):
        if artifact.available_at > context.decision_time:
            fail("P7_LTR_RUNTIME_ARTIFACT_FUTURE_DATED", f"{artifact.artifact_name} unavailable at decision time")
    policy = RuntimePolicy.model_validate(config.get("runtime_policy"))
    reports, references = resolve_runtime_model(models.records, qualification.records, governance.records,
                                                candidates, tournament["metric_semantics_registry"].records,
                                                policy, context.decision_time)
    outputs = {
        "runtime_model_compatibility_report": build_artifact(name="runtime_model_compatibility_report", producer_module_id=MODULE_ID, records=reports, context=context),
        "resolved_runtime_model_reference": build_artifact(name="resolved_runtime_model_reference", producer_module_id=MODULE_ID, records=references, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"resolved_count": len(references), "candidate_count": len(candidates)})
