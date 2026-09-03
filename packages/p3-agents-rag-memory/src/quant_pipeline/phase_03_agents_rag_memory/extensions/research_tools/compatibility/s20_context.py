"""Pure S20-to-S21 context projection with compact authorized tool descriptors."""

from __future__ import annotations

from collections import defaultdict
import json
from collections.abc import Mapping, Sequence
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_hashing import stable_id
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus as S21ArtifactStatus,
    CognitionConfig,
    LineageRecord as S21LineageRecord,
    PersonContextRecord as S21PersonContextRecord,
    PersonToolEntitlementPanel as S21PersonToolEntitlementPanel,
    ValidatedPersonContextBundle as S21ValidatedPersonContextBundle,
)
from quant_pipeline.phase_03_agents_rag_memory.s20.adapters import RegexTokenizer

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    ResearchModeRegistry,
)
from ..contracts.capability_artifacts import (
    ContextDescriptorRecord,
    ContextProjectionAudit,
    ContextProjectionRecord,
    PersonResearchCapabilityPanel,
    ResearchPlanRegistry,
)
from ..contracts.capability_configs import ContextToolDescriptorPolicyConfig
from ..core.errors import fail
from ..core.hashing import content_hash
from ..services.artifact_construction import finalize, lineage, python_value
from ..services.input_contracts import parse_datetime


def _mapping(value: object) -> Mapping[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        raise fail("P3RT-CONTRACT-3440", "context projection input must be a mapping")
    return raw


def _records(value: object) -> list[Mapping[str, Any]]:
    raw = _mapping(value)
    rows = raw.get("records", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _snapshot(snapshot: object) -> tuple[str, str, str, Any]:
    raw = _mapping(snapshot)
    run_id = str(raw.get("run_id") or "run-research-tools")
    cycle_id = str(raw.get("cycle_id") or "cycle-research-tools")
    snapshot_id = str(raw.get("snapshot_id") or raw.get("artifact_id") or "snapshot-research-tools")
    as_of = raw.get("as_of") or raw.get("as_of_time") or raw.get("decision_time")
    if as_of is None:
        raise fail("P3RT-PIT-3441", "phase3_run_snapshot must expose as_of or decision_time")
    parsed = parse_datetime(as_of)
    if parsed is None:
        raise fail("P3RT-PIT-3441", "phase3_run_snapshot decision time is invalid")
    return run_id, cycle_id, snapshot_id, parsed


def _seed_index(panel: object) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in _records(panel):
        person_id = str(row.get("person_id", ""))
        seed = row.get("person_seed", row.get("seed"))
        if person_id and isinstance(seed, int):
            result[person_id] = seed
    return result


def _section_text(sections: Sequence[Mapping[str, Any]], section_type: str) -> str:
    values = [str(item.get("text", item.get("content", ""))) for item in sections if str(item.get("section_type")) == section_type]
    return "\n".join(value for value in values if value).strip()


def _evidence_refs(sections: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    values: set[str] = set()
    for item in sections:
        if str(item.get("section_type")) != "RETRIEVED_EVIDENCE":
            continue
        for key in ("source_refs", "item_ids", "evidence_refs"):
            raw = item.get(key, ())
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                values.update(str(value) for value in raw)
    return tuple(sorted(values))


def _base_prompt(sections: Sequence[Mapping[str, Any]]) -> str:
    chunks: list[str] = []
    for item in sections:
        section_type = str(item.get("section_type") or item.get("section_id") or "CONTEXT")
        text = str(item.get("text", item.get("content", ""))).strip()
        if text:
            chunks.append(f"## {section_type}\n{text}")
    return "\n\n".join(chunks)


def _required_arguments(schema: Mapping[str, Any]) -> tuple[str, ...]:
    raw = schema.get("required", ())
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return tuple(sorted(str(item) for item in raw))
    return ()


def build_context_overlay(
    *,
    validated_person_context_bundle: object,
    entitlement_panel: S21PersonToolEntitlementPanel,
    capability_panel: PersonResearchCapabilityPanel,
    plan_registry: ResearchPlanRegistry,
    tool_catalog: CanonicalResearchToolCatalog,
    operation_registry: CanonicalToolOperationRegistry,
    mode_registry: ResearchModeRegistry,
    person_seed_panel: object,
    phase3_run_snapshot: object,
    cognition_config: CognitionConfig,
    descriptor_policy: ContextToolDescriptorPolicyConfig,
) -> tuple[S21ValidatedPersonContextBundle, ContextProjectionAudit]:
    del plan_registry
    run_id, cycle_id, snapshot_id, decision_time = _snapshot(phase3_run_snapshot)
    source_bundle = _mapping(validated_person_context_bundle)
    if str(source_bundle.get("run_id")) != run_id or str(source_bundle.get("cycle_id")) != cycle_id:
        raise fail("P3RT-CONTRACT-3442", "S20 context and phase3 snapshot run/cycle must match")
    seeds = _seed_index(person_seed_panel)
    operations = {(item.tool_id, item.operation_id): item for item in operation_registry.operations}
    mode_costs = defaultdict(dict)
    for mode in mode_registry.modes:
        mode_costs[(mode.tool_id, mode.operation_id)][mode.mode_id] = mode.internal_work_units
    capability_scores: dict[tuple[str, str], float] = {
        (item.person_id, item.capability_id): item.score for item in capability_panel.records
    }
    mode_requirements: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for mode in mode_registry.modes:
        mode_requirements[(mode.tool_id, mode.operation_id, mode.mode_id)] = tuple(
            sorted(set((*mode.required_capabilities, *mode.required_methods)))
        )
    entitlements_by_person: dict[str, list[Any]] = defaultdict(list)
    for entitlement in entitlement_panel.records:
        entitlements_by_person[entitlement.person_id].append(entitlement)

    tokenizer = RegexTokenizer()
    output_records: list[S21PersonContextRecord] = []
    audit_records: list[ContextProjectionRecord] = []
    descriptor_records: list[ContextDescriptorRecord] = []
    source_context_rows = _records(validated_person_context_bundle)
    for wrapper in sorted(source_context_rows, key=lambda item: str(_mapping(item.get("context", {})).get("person_id", ""))):
        context = _mapping(wrapper.get("context", {}))
        budget_report = _mapping(wrapper.get("budget_report", {}))
        person_id = str(context.get("person_id", ""))
        if not person_id:
            raise fail("P3RT-CONTRACT-3443", "S20 context record is missing person_id")
        if person_id not in seeds:
            raise fail("P3RT-DATA-3444", "person seed is required for deterministic S21 context", {"person_id": person_id})
        as_of = parse_datetime(context.get("as_of"))
        if as_of != decision_time:
            raise fail("P3RT-PIT-3445", "S20 context as_of must equal phase3 decision_time", {"person_id": person_id})
        sections_raw = context.get("sections", ())
        sections = [item for item in sections_raw if isinstance(item, Mapping)] if isinstance(sections_raw, Sequence) else []
        base_prompt = _base_prompt(sections)
        base_tokens = tokenizer.count(base_prompt)
        context_limit = int(budget_report.get("effective_budget") or 1)
        descriptors: list[tuple[float, str, ContextDescriptorRecord]] = []
        for entitlement in sorted(entitlements_by_person.get(person_id, []), key=lambda item: item.tool_id):
            tool_operations = sorted(entitlement.operations, key=lambda item: item.operation_id)
            for operation in tool_operations[: descriptor_policy.max_operations_per_tool]:
                spec = operations[(entitlement.tool_id, operation.operation_id)]
                modes = tuple(operation.arguments_schema.get("properties", {}).get("research_mode", {}).get("enum", ()))
                required = _required_arguments(operation.arguments_schema)
                cost_text = "/".join(f"{mode}:{mode_costs[(entitlement.tool_id, operation.operation_id)].get(mode, '?')}" for mode in modes)
                example_key = f"{entitlement.tool_id}/{operation.operation_id}"
                example = descriptor_policy.operation_examples.get(example_key)
                example_text = ""
                if descriptor_policy.include_examples and example:
                    raw_example = json.dumps(example, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    example_text = f" Example={raw_example[:descriptor_policy.max_example_characters]}."
                text = (
                    f"TOOL={entitlement.tool_id}; OPERATION={operation.operation_id}; "
                    f"PURPOSE={spec.description}; MODES={','.join(modes)}; "
                    f"REQUIRED={','.join(required) or 'none'}; COST={cost_text or 'n/a'}; "
                    "LIMITS=read-only, point-in-time, evidence-bound, no trade/signal/backtest."
                    f"{example_text}"
                )
                estimated = tokenizer.count(text)
                mode_relevance: list[float] = []
                for mode_id in modes:
                    required_ids = mode_requirements.get((entitlement.tool_id, operation.operation_id, mode_id), ())
                    if required_ids:
                        mode_relevance.append(min(capability_scores.get((person_id, item), 0.0) for item in required_ids))
                    else:
                        mode_relevance.append(1.0)
                relevance = max(mode_relevance, default=0.0)
                record = ContextDescriptorRecord(
                    person_id=person_id, tool_id=entitlement.tool_id,
                    operation_id=operation.operation_id, mode_ids=modes,
                    descriptor_text=text, estimated_tokens=estimated,
                    included=False, reason_codes=(),
                )
                descriptors.append((relevance, example_key, record))
        descriptors.sort(key=lambda item: (-item[0], item[1]))
        header_lines = [descriptor_policy.section_header, *descriptor_policy.mandatory_instructions]
        selected_texts: list[str] = []
        selected_tokens = tokenizer.count("\n".join(header_lines))
        omitted: list[str] = []
        for _, ref, descriptor in descriptors:
            projected = selected_tokens + descriptor.estimated_tokens
            final_projected = tokenizer.count(base_prompt + "\n\n## " + "\n".join(header_lines + selected_texts + [descriptor.descriptor_text]))
            if projected <= descriptor_policy.max_descriptor_tokens and final_projected <= context_limit:
                selected_texts.append(descriptor.descriptor_text)
                selected_tokens = projected
                descriptor_records.append(descriptor.model_copy(update={"included": True}))
            else:
                omitted.append(ref)
                descriptor_records.append(descriptor.model_copy(update={"reason_codes": ("P3RT-BUDGET-3446",)}))
        tool_block = "\n".join(header_lines + selected_texts)
        prompt_context = base_prompt + (f"\n\n## {tool_block}" if tool_block else "")
        final_tokens = tokenizer.count(prompt_context)
        if final_tokens > context_limit:
            raise fail("P3RT-BUDGET-3447", "mandatory S20 context plus tool policy exceeds context limit", {"person_id": person_id})
        person_entitlements = entitlements_by_person.get(person_id, [])
        allowed_tool_ids = tuple(sorted(item.tool_id for item in person_entitlements))
        budgets = [item.budget_calls_per_cycle for item in person_entitlements]
        tool_budget = min([cognition_config.max_tool_calls_per_cycle, 5, *budgets]) if budgets else 0
        activation_id = str(context.get("activation_id") or stable_id("activation", run_id, cycle_id, context.get("context_id"), person_id))
        transaction_id = stable_id("cognition", run_id, cycle_id, context.get("context_id"), person_id, snapshot_id)
        source_id = str(context.get("context_id") or stable_id("context", person_id, snapshot_id))
        output_records.append(S21PersonContextRecord(
            run_id=run_id, cycle_id=cycle_id, activation_id=activation_id,
            cognition_transaction_id=transaction_id, person_id=person_id,
            snapshot_id=snapshot_id, as_of=decision_time, seed=seeds[person_id],
            personality_summary=_section_text(sections, "PERSON_IDENTITY") or f"Person {person_id}",
            current_belief_summary=_section_text(sections, "PRIOR_BELIEFS"),
            prompt_context=prompt_context,
            retrieved_evidence_refs=_evidence_refs(sections),
            allowed_tool_ids=allowed_tool_ids,
            tool_budget=tool_budget,
            context_token_count=final_tokens,
            context_token_limit=context_limit,
            lineage=S21LineageRecord(
                lineage_id=stable_id("lin", "P3.S34.M05", source_id, entitlement_panel.lineage.lineage_id),
                source_artifact_ids=(source_id, entitlement_panel.lineage.lineage_id),
                source_hashes={
                    source_id: content_hash(context),
                    entitlement_panel.lineage.lineage_id: content_hash(entitlement_panel.model_dump(mode="json")),
                },
                producer_module_id="P3.S34.M05",
            ),
        ))
        audit_records.append(ContextProjectionRecord(
            person_id=person_id, source_context_id=source_id, activation_id=activation_id,
            cognition_transaction_id=transaction_id, source_token_count=base_tokens,
            descriptor_token_count=selected_tokens, final_token_count=final_tokens,
            context_token_limit=context_limit, allowed_tool_ids=allowed_tool_ids,
            omitted_operation_refs=tuple(sorted(omitted)),
            warnings=("P3RT-BUDGET-3446",) if omitted else (),
        ))

    source_hash = str(source_bundle.get("content_hash") or content_hash(source_bundle))
    lineage_ids = tuple(sorted({item.lineage.lineage_id for item in output_records}))
    output_lineage = S21LineageRecord(
        lineage_id=stable_id("lin", "P3.S34.M05.bundle", lineage_ids),
        source_artifact_ids=lineage_ids,
        source_hashes={item: content_hash(item) for item in lineage_ids},
        producer_module_id="P3.S34.M05",
    )
    bundle_status = S21ArtifactStatus.READY if output_records else S21ArtifactStatus.EMPTY_VALID
    bundle = S21ValidatedPersonContextBundle(
        status=bundle_status, items=tuple(output_records), lineage=output_lineage,
    )
    audit_status = ArtifactStatus.DEGRADED if any(item.warnings for item in audit_records) else ArtifactStatus.READY
    audit = finalize(ContextProjectionAudit, {
        "status": audit_status,
        "lineage": lineage("P3.S34.M05", descriptor_policy.policy_version, (
            validated_person_context_bundle, entitlement_panel, capability_panel,
            tool_catalog, operation_registry, mode_registry, person_seed_panel,
            phase3_run_snapshot, cognition_config, descriptor_policy,
        )),
        "records": tuple(audit_records),
        "descriptors": tuple(sorted(descriptor_records, key=lambda item: (item.person_id, item.tool_id, item.operation_id))),
        "source_bundle_hash": source_hash,
        "reason_codes": () if audit_status is ArtifactStatus.READY else ("P3RT-BUDGET-3446",),
    })
    return bundle, audit
