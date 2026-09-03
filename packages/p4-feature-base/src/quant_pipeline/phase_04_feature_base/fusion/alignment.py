from __future__ import annotations
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime

from ..artifact_protocol import stable_hash
from ..economic_models import MissingnessState, QualityState
from ..perspective_models import PerspectiveExecutionRegistry, PerspectiveFeatureRecord
from ..fusion_models import AlignmentPolicyRegistry, AlignedPerspectiveRecord


def _local_entities(records:list[PerspectiveFeatureRecord], global_ids:set[str], excluded:set[str]) -> tuple[str,...]:
    return tuple(sorted({r.entity_id for r in records if r.entity_id not in global_ids and r.entity_id not in excluded}))


def _broadcast_map(policy:AlignmentPolicyRegistry, local_entities:tuple[str,...]) -> dict[str,tuple[str,tuple[str,...]]]:
    result={}
    for rule in policy.broadcast_rules:
        targets=tuple(entity for entity in local_entities if entity not in set(rule.excluded_target_entity_ids))
        result[rule.feature_id]=(rule.source_entity_id,targets)
    return result


def _candidate_entities(feature_id:str, entity_id:str, broadcasts:dict[str,tuple[str,tuple[str,...]]]) -> tuple[str,...]:
    rule=broadcasts.get(feature_id)
    if rule and entity_id in rule[1]:
        return (entity_id,rule[0])
    return (entity_id,)


def _missing_record(*,anchor:datetime,entity_id:str,spec,reason:MissingnessState,source:PerspectiveFeatureRecord|None,policy_lineage:str) -> AlignedPerspectiveRecord:
    lineage=source.record_lineage_id if source else f"lineage-p4-s6-missing-{stable_hash([entity_id,spec.feature_id,anchor,policy_lineage])[:20]}"
    available_at=source.available_at if source else anchor
    return AlignedPerspectiveRecord(
        decision_time=anchor,source_decision_time=source.decision_time if source else None,entity_id=entity_id,
        feature_id=spec.feature_id,hypothesis_id=spec.hypothesis_id,phenomenon_id=spec.phenomenon_id,
        perspective_id=spec.perspective_id,observer_id=spec.observer_id,parameterization_id=spec.parameterization_id,
        horizon_group=spec.horizon_group,value=None,unit=source.unit if source else "unknown",
        sign_convention=source.sign_convention if source else "UNAVAILABLE",available_at=available_at,
        information_age_seconds=(anchor-source.decision_time).total_seconds() if source else None,
        source_modalities=source.source_modalities if source else (),source_feature_ids=source.source_feature_ids if source else spec.source_feature_ids,
        quality_state=QualityState.DEGRADED,missingness_state=reason,record_lineage_id=lineage,
        attributes={"alignment_status":reason.value,"broadcast_source_entity":source.entity_id if source and source.entity_id!=entity_id else None},
    )


def align_perspectives(*,records:list[PerspectiveFeatureRecord],registry:PerspectiveExecutionRegistry,policy:AlignmentPolicyRegistry) -> list[AlignedPerspectiveRecord]:
    enabled=tuple(spec for spec in registry.records if spec.enabled)
    global_ids=set(policy.global_entity_ids)
    excluded=set().union(*(set(rule.excluded_target_entity_ids) for rule in policy.broadcast_rules))
    local_entities=_local_entities(records,global_ids,excluded)
    broadcasts=_broadcast_map(policy,local_entities)
    series=defaultdict(list)
    for row in records:
        series[(row.entity_id,row.feature_id,row.parameterization_id)].append(row)
    for values in series.values(): values.sort(key=lambda r:r.decision_time)
    times={key:[row.decision_time for row in values] for key,values in series.items()}
    anchors=defaultdict(set)
    for row in records:
        if row.entity_id not in global_ids and row.entity_id not in excluded:
            anchors[(row.entity_id,row.horizon_group)].add(row.decision_time)
    policies={row.horizon_group:row for row in policy.policies}
    out=[]
    for (entity,horizon),anchor_values in sorted(anchors.items(),key=lambda x:(x[0][0],x[0][1])):
        horizon_policy=policies.get(horizon)
        if horizon_policy is None: continue
        specs=[spec for spec in enabled if spec.horizon_group==horizon]
        for anchor in sorted(anchor_values):
            for spec in specs:
                source=None
                for source_entity in _candidate_entities(spec.feature_id,entity,broadcasts):
                    key=(source_entity,spec.feature_id,spec.parameterization_id)
                    available=series.get(key,[])
                    if not available: continue
                    pos=bisect_right(times[key],anchor)-1
                    while pos>=0 and available[pos].available_at>anchor: pos-=1
                    if pos>=0:
                        source=available[pos]; break
                if source is None:
                    if horizon_policy.emit_missing_records: out.append(_missing_record(anchor=anchor,entity_id=entity,spec=spec,reason=MissingnessState.STRUCTURALLY_MISSING,source=None,policy_lineage=policy.lineage_id))
                    continue
                age=(anchor-source.decision_time).total_seconds()
                if age>horizon_policy.max_age_seconds:
                    if horizon_policy.emit_missing_records: out.append(_missing_record(anchor=anchor,entity_id=entity,spec=spec,reason=MissingnessState.STALE,source=source,policy_lineage=policy.lineage_id))
                    continue
                out.append(AlignedPerspectiveRecord(
                    decision_time=anchor,source_decision_time=source.decision_time,entity_id=entity,feature_id=source.feature_id,
                    hypothesis_id=source.hypothesis_id,phenomenon_id=source.phenomenon_id,perspective_id=source.perspective_id,
                    observer_id=source.observer_id,parameterization_id=source.parameterization_id,horizon_group=source.horizon_group,
                    value=source.value,unit=source.unit,sign_convention=source.sign_convention,available_at=source.available_at,
                    information_age_seconds=age,source_modalities=source.source_modalities,source_feature_ids=source.source_feature_ids,
                    quality_state=source.quality_state,missingness_state=source.missingness_state,record_lineage_id=source.record_lineage_id,
                    attributes={**source.attributes,"alignment_status":"OBSERVED","broadcast_source_entity":source.entity_id if source.entity_id!=entity else None},
                ))
                if len(out)>policy.max_output_records:
                    raise ValueError("aligned output exceeds max_output_records")
            if len(out)>policy.max_output_records:
                raise ValueError("aligned output exceeds max_output_records")
    return out
