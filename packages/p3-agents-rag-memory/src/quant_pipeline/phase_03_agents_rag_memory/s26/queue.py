"""P3.S26.M02 — deterministic N+1 endogenous queue."""
from __future__ import annotations
from collections import defaultdict
from .artifacts import *
from .common import content_hash, derived_id, lineage_id, log_event, require_not_future, require_same_context
from .errors import S26ContractError
from .types import StimulusBusConfig, StimulusOrigin
MODULE_ID="P3.S26.M02"

def _make(origin: StimulusOrigin, event, snapshot: Phase3RunSnapshot, config: StimulusBusConfig, *, person: str, source_id: str, created, available, priority: float, subject: str, evidence: tuple[str,...], lineage: str, parent: str|None=None, underlying: str|None=None, proposition: str|None=None)->EndogenousStimulus:
    payload={"origin":origin.value,"source":source_id,"person":person,"subject":subject,"underlying":underlying,"proposition":proposition,"target_cycle":snapshot.next_cycle_id}
    return EndogenousStimulus(stimulus_id=derived_id("stim",*payload.values()),origin_type=origin,source_event_id=source_id,causal_parent_id=parent,
        target_person_id=person,subject=subject,underlying_id=underlying,proposition_id=proposition,created_cycle=snapshot.cycle_id,
        target_cycle=snapshot.next_cycle_id,created_at=created,available_at=available,
        expires_after_cycle=snapshot.next_cycle_id+config.ttl_cycles_by_origin[origin.value]-1,
        priority=min(1,config.priority_by_origin[origin.value]*priority),evidence_refs=evidence,source_lineage_ids=(lineage,),content_hash=content_hash(payload))

def _key(x: EndogenousStimulus)->tuple[object,...]:
    return (x.origin_type.value,x.source_event_id,x.target_person_id,x.proposition_id or x.subject,x.target_cycle)

def _merge(stimuli: list[EndogenousStimulus])->list[EndogenousStimulus]:
    out={}
    for item in sorted(stimuli,key=lambda x:(_key(x),x.stimulus_id)):
        key=_key(item); old=out.get(key)
        if old is None: out[key]=item; continue
        if (old.subject,old.underlying_id,old.proposition_id)!=(item.subject,item.underlying_id,item.proposition_id):
            raise S26ContractError("dedup collision contains conflicting content")
        out[key]=old.model_copy(update={"priority":max(old.priority,item.priority),"available_at":min(old.available_at,item.available_at),
            "evidence_refs":tuple(sorted(set(old.evidence_refs+item.evidence_refs))),"source_lineage_ids":tuple(sorted(set(old.source_lineage_ids+item.source_lineage_ids)))})
    return list(out.values())

def build_next_cycle_queue(**raw)->NextCycleEndogenousStimulusQueue:
    tools=ToolDiscoveryEventPanel.model_validate(raw["tool_discovery_event_panel"]); social=SocialDeliveryEventPanel.model_validate(raw["social_delivery_event_panel"])
    memory=MemoryTriggerEventPanel.model_validate(raw["memory_trigger_event_panel"]); attention=FinalizedAttentionFollowupIntentPanel.model_validate(raw["finalized_attention_followup_intent_panel"])
    snapshot=Phase3RunSnapshot.model_validate(raw["phase3_run_snapshot"]); config=StimulusBusConfig.model_validate(raw["stimulus_bus_config"])
    require_same_context(tools,social,memory,attention,snapshot); stimuli=[]; allowed={x.value for x in config.allowed_sources}
    if StimulusOrigin.TOOL_DISCOVERY.value in allowed:
        for x in tools.records:
            require_not_future(x.available_at,as_of=snapshot.as_of_time,label="tool discovery")
            stimuli.append(_make(StimulusOrigin.TOOL_DISCOVERY,x,snapshot,config,person=x.person_id,source_id=x.event_id,created=x.discovered_at,available=x.available_at,
                priority=x.source_priority,subject=x.subject,evidence=x.evidence_refs,lineage=x.lineage_id,parent=x.source_request_id,underlying=x.underlying_id,proposition=x.proposition_id))
    if StimulusOrigin.SOCIAL_DELIVERY.value in allowed:
        allowed_status=set(config.allowed_social_statuses)
        for x in social.records:
            require_not_future(x.available_at,as_of=snapshot.as_of_time,label="social delivery")
            if x.status not in allowed_status: raise S26ContractError(f"social status not queueable: {x.status.value}")
            stimuli.append(_make(StimulusOrigin.SOCIAL_DELIVERY,x,snapshot,config,person=x.receiver_person_id,source_id=x.event_id,created=x.occurred_at,available=x.available_at,
                priority=x.source_priority,subject=x.subject,evidence=x.evidence_refs,lineage=x.lineage_id,parent=x.causal_parent_id or x.message_id,underlying=x.underlying_id,proposition=x.proposition_id))
    if StimulusOrigin.MEMORY_TRIGGER.value in allowed:
        for x in memory.records:
            require_not_future(x.available_at,as_of=snapshot.as_of_time,label="memory trigger")
            if x.target_cycle!=snapshot.next_cycle_id: raise S26ContractError("memory trigger must target N+1")
            stimuli.append(_make(StimulusOrigin.MEMORY_TRIGGER,x,snapshot,config,person=x.person_id,source_id=x.event_id,created=x.created_at,available=x.available_at,
                priority=x.trigger_score,subject=x.subject,evidence=x.evidence_refs,lineage=x.lineage_id,parent=x.causal_parent_id or x.memory_id,underlying=x.underlying_id,proposition=x.proposition_id))
    if StimulusOrigin.ATTENTION_FOLLOWUP.value in allowed:
        for x in attention.records:
            require_not_future(x.available_at,as_of=snapshot.as_of_time,label="attention followup")
            stimuli.append(_make(StimulusOrigin.ATTENTION_FOLLOWUP,x,snapshot,config,person=x.person_id,source_id=x.intent_id,created=x.created_at,available=x.available_at,
                priority=x.priority,subject=x.subject,evidence=x.evidence_refs,lineage=x.lineage_id,parent=x.causal_parent_id,underlying=x.underlying_id,proposition=x.proposition_id))
    if config.require_evidence and any(not x.evidence_refs for x in stimuli): raise S26ContractError("all stimuli require evidence")
    merged=_merge(stimuli); counts=defaultdict(int)
    for x in merged: counts[x.target_person_id]+=1
    exceeded={p:n for p,n in counts.items() if n>config.max_stimuli_per_person}
    if exceeded: raise S26ContractError(f"stimulus budget exceeded: {exceeded}")
    ordered=tuple(sorted(merged,key=lambda x:(x.target_cycle,x.available_at,-x.priority,x.target_person_id,x.stimulus_id)))
    line=lineage_id(MODULE_ID,"next_cycle_endogenous_stimulus_queue",(tools.lineage_id,social.lineage_id,memory.lineage_id,attention.lineage_id,snapshot.lineage_id))
    payload={"schema_version":"p3.s26.next_cycle_endogenous_stimulus_queue.v2","run_id":snapshot.run_id,"cycle_id":snapshot.cycle_id,"as_of_time":snapshot.as_of_time,
        "lineage_id":line,"queue_id":derived_id("queue",snapshot.run_id,snapshot.cycle_id,snapshot.next_cycle_id),"source_cycle_id":snapshot.cycle_id,
        "target_cycle_id":snapshot.next_cycle_id,"stimuli":ordered}
    result=NextCycleEndogenousStimulusQueue(**payload,content_hash=content_hash(payload))
    log_event("module_succeeded",module_id=MODULE_ID,run_id=snapshot.run_id,cycle_id=snapshot.cycle_id,status="PASS",output_record_count=len(result.stimuli))
    return result
