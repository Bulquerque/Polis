from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from math import fsum
from time import perf_counter
from typing import Any, Mapping

from ...s30_models import (
    AgentDisagreementPanel, ContextMemoryFeaturePanel, EvidenceRelation,
    EvidenceTagPanel, EvidenceTagRecord, ExecutionContext, HypothesisRecord,
    HypothesisRegistry, PropositionDefinition, PropositionRegistryConfig,
    QualityStatus, SocialFeaturePanel,
)
from .common import (
    S30ContractError, _artifact_id, _lineage_id, _module_result, _parse,
    _quality_rollup, _scan_forbidden, _unique_index, _validate_artifact_alignment,
)

def _registry_by_id(config: PropositionRegistryConfig) -> dict[str, PropositionDefinition]:
    return {item.proposition_id: item for item in config.propositions}


def build_hypothesis_registry(
    inputs: Mapping[str, Any],
    context_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Build deterministic, falsifiable hypotheses from approved projections and evidence."""

    started_at = perf_counter()
    _scan_forbidden(inputs)
    _scan_forbidden(context_value)
    required = {
        "social_feature_panel",
        "context_memory_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "proposition_registry_config",
    }
    missing = sorted(required - set(inputs))
    if missing:
        raise S30ContractError(f"P3.S30.M03 missing required inputs: {missing}")

    context = _parse(ExecutionContext, context_value, "execution_context")
    social_panel = _parse(SocialFeaturePanel, inputs["social_feature_panel"], "social_feature_panel")
    memory_panel = _parse(
        ContextMemoryFeaturePanel,
        inputs["context_memory_feature_panel"],
        "context_memory_feature_panel",
    )
    evidence_panel = _parse(EvidenceTagPanel, inputs["evidence_tag_panel"], "evidence_tag_panel")
    disagreement_panel = _parse(
        AgentDisagreementPanel,
        inputs["agent_disagreement_panel"],
        "agent_disagreement_panel",
    )
    proposition_config = _parse(
        PropositionRegistryConfig,
        inputs["proposition_registry_config"],
        "proposition_registry_config",
    )
    _validate_artifact_alignment(
        context,
        (social_panel, memory_panel, evidence_panel, disagreement_panel),
    )
    propositions = _registry_by_id(proposition_config)

    social_grains = {
        (record.underlying, record.proposition_id, record.horizon)
        for record in social_panel.records
    }
    memory_grains = {
        (record.underlying, record.proposition_id, record.horizon)
        for record in memory_panel.records
    }
    if social_grains != memory_grains:
        raise S30ContractError("grain mismatch between social and context/memory features")

    evidence_by_key: dict[tuple[str, str, str], list[EvidenceTagRecord]] = defaultdict(list)
    for record in evidence_panel.records:
        evidence_by_key[(record.underlying, record.proposition_id, record.horizon)].append(record)
    disagreement_by_key = _unique_index(
        disagreement_panel.records,
        lambda item: (item.underlying, item.proposition_id, item.horizon),
        "agent disagreement hypothesis grain",
    )

    records: list[HypothesisRecord] = []
    reasons: set[str] = set()
    for grain in sorted(social_grains):
        underlying, proposition_id, horizon = grain
        definition = propositions.get(proposition_id)
        if definition is None:
            raise S30ContractError(f"unknown proposition_id {proposition_id!r}")
        if horizon not in definition.allowed_horizons:
            raise S30ContractError(
                f"horizon {horizon!r} is not allowed for proposition {proposition_id!r}"
            )
        disagreement = disagreement_by_key.get(grain)
        if disagreement is None:
            raise S30ContractError(f"missing disagreement record for grain {grain!r}")
        evidence = evidence_by_key.get(grain, [])
        eligible = [
            item
            for item in evidence
            if definition.allow_context_only
            or item.evidence_relation != EvidenceRelation.CONTEXT_ONLY
        ]
        if len(eligible) < definition.minimum_evidence_count:
            reasons.add(f"INSUFFICIENT_EVIDENCE:{underlying}:{proposition_id}:{horizon}")
            continue

        supporting = tuple(
            sorted(item.evidence_id for item in evidence if item.evidence_relation == EvidenceRelation.SUPPORTS)
        )
        opposing = tuple(
            sorted(item.evidence_id for item in evidence if item.evidence_relation == EvidenceRelation.OPPOSES)
        )
        context_refs = tuple(
            sorted(item.evidence_id for item in evidence if item.evidence_relation == EvidenceRelation.CONTEXT_ONLY)
        )
        quality_status = _quality_rollup(
            tuple(item.quality_status for item in evidence) + (disagreement.quality_status,)
        )
        quality_reasons = set(disagreement.quality_reasons)
        for item in evidence:
            quality_reasons.update(item.quality_reasons)
        if not supporting and not opposing:
            quality_status = QualityStatus.BLOCKED
            quality_reasons.add("NO_DIRECTIONAL_EVIDENCE")

        source_quality = fsum(item.source_quality_score for item in evidence) / len(evidence)
        statement = definition.statement_template.format(
            underlying=underlying,
            horizon=horizon,
            proposition=definition.title,
        )
        falsification = definition.falsification_template.format(
            underlying=underlying,
            horizon=horizon,
            proposition=definition.title,
            observable=definition.required_observable,
        )
        maturity = context.created_at + timedelta(days=definition.maturity_days)
        hypothesis_payload = {
            "grain": grain,
            "statement": statement,
            "falsification": falsification,
            "supporting": supporting,
            "opposing": opposing,
            "context": context_refs,
            "registry": (proposition_config.registry_id, proposition_config.registry_version),
        }
        hypothesis_id = _artifact_id("hypothesis", hypothesis_payload)
        records.append(
            HypothesisRecord(
                hypothesis_id=hypothesis_id,
                artifact_id=hypothesis_id,
                created_at=context.created_at,
                as_of_time=context.as_of_time,
                matures_at=maturity,
                underlying_id=underlying,
                proposition_id=proposition_id,
                horizon=horizon,
                hypothesis_text=statement,
                supporting_evidence_refs=supporting,
                opposing_evidence_refs=opposing,
                context_evidence_refs=context_refs,
                evidence_count=len(evidence),
                source_quality_score=source_quality,
                falsification_criterion=falsification,
                required_observable=definition.required_observable,
                quality_status=quality_status,
                quality_reasons=tuple(sorted(quality_reasons)),
                lineage_id=_lineage_id("hypothesis", hypothesis_payload),
                pipeline_version=context.pipeline_version,
            )
        )

    records.sort(key=lambda item: (item.underlying_id, item.proposition_id, item.horizon))
    statuses = [record.quality_status for record in records]
    output_status = _quality_rollup(statuses) if statuses else QualityStatus.BLOCKED
    payload = [record.model_dump(mode="json") for record in records]
    output = HypothesisRegistry(
        artifact_id=_artifact_id("hypothesis-registry", payload),
        created_at=context.created_at,
        lineage_id=_lineage_id(
            "hypothesis-registry",
            {
                "social": social_panel.lineage_id,
                "memory": memory_panel.lineage_id,
                "evidence": evidence_panel.lineage_id,
                "disagreement": disagreement_panel.lineage_id,
                "registry": (
                    proposition_config.registry_id,
                    proposition_config.registry_version,
                ),
                "records": payload,
            },
        ),
        pipeline_version=context.pipeline_version,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        schema_id="p3.s30.hypothesis_registry.semantic",
        schema_version="1.0.0",
        quality_status=output_status,
        quality_reasons=tuple(sorted(reasons)),
        records=tuple(records),
    )
    _scan_forbidden(output)
    return _module_result(
        "P3.S30.M03",
        "hypothesis_registry_builder",
        "hypothesis_registry",
        output,
        started_at,
    )
