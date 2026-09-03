"""P3.S26.M01 — deterministic person-scoped memory consolidation."""
from __future__ import annotations
from collections import defaultdict
from .artifacts import *
from .common import clamp, content_hash, derived_id, lineage_id, log_event, require_not_future, require_same_context
from .errors import S26ContractError, S26PolicyError
from .types import *
MODULE_ID="P3.S26.M01"

def _patch(config: MemoryConsolidationConfig, patch: ActiveRetroPolicyPatch, cycle: int)->MemoryConsolidationConfig:
    if patch.status==RetroPatchStatus.NO_PATCH:
        if patch.parameters: raise S26PolicyError("NO_PATCH cannot carry parameters")
        return config
    if patch.effective_cycle_id>cycle or patch.change_target!="memory_consolidation_config":
        raise S26PolicyError("Retro patch is not effective or targets another surface")
    reject_forbidden_memory_patch(patch.parameters)
    if len(patch.parameters)!=1: raise S26PolicyError("Retro-managed patch must change one parameter")
    key,value=next(iter(patch.parameters.items()))
    if key not in config.allowed_patch_parameters: raise S26PolicyError(f"patch key not allowed: {key}")
    return MemoryConsolidationConfig.model_validate({**config.model_dump(mode="python"),key:value})

def _new_item(person: str, kind: MemoryType, content_ref: str, fingerprint: str, events: tuple[str,...], evidence: tuple[str,...], created, importance: float, confidence: float, cycle: int, lineage: str, retrievability: float)->MemoryItem:
    return MemoryItem(memory_id=derived_id("mem",person,kind.value,fingerprint),person_id=person,memory_type=kind,
        source_event_ids=events,created_at=created,available_at=created,valid_from_cycle=cycle+1,importance=importance,
        confidence=confidence,retrievability=retrievability,content_ref=content_ref,content_fingerprint=fingerprint,
        evidence_refs=evidence,status=MemoryStatus.ACTIVE,reinforcement_count=1,last_reinforced_at=created,
        protected_audit=False,lineage_ids=(lineage,))

def _candidates(trajectories: PersonLearningTrajectoryBundle, beliefs: NextBeliefStatePanel, persons: ValidatedNextPersonStatePanel,
                social: SocialDeliveryPanel, feedback: ActiveBeliefFeedbackBundle, config: MemoryConsolidationConfig)->list[MemoryItem]:
    cycle=persons.cycle_id; result=[]; known={x.person_id for x in persons.records}
    type_map={ExperienceType.GENERAL:MemoryType.EPISODIC,ExperienceType.TOOL_DISCOVERY:MemoryType.TOOL_EXPERIENCE,
              ExperienceType.SOCIAL_INTERACTION:MemoryType.SOCIAL,ExperienceType.BELIEF_UPDATE:MemoryType.SEMANTIC}
    for x in trajectories.items:
        require_not_future(x.available_at,as_of=trajectories.as_of_time,label="experience")
        result.append(_new_item(x.person_id,type_map[x.experience_type],x.content_ref,x.content_fingerprint,x.source_event_ids,
            x.evidence_refs,x.available_at,x.importance,x.confidence,cycle,x.lineage_id,config.initial_retrievability))
    for x in beliefs.records:
        require_not_future(x.changed_at,as_of=beliefs.as_of_time,label="belief")
        if abs(x.delta)>=config.belief_delta_memory_threshold:
            fp=content_hash({"person":x.person_id,"proposition":x.proposition_id,"horizon":x.horizon,"value":x.new_value})
            result.append(_new_item(x.person_id,MemoryType.SEMANTIC,f"belief:{x.underlying_id}:{x.proposition_id}:{x.horizon}",fp,
                (x.commitment_id,),x.evidence_refs,x.changed_at,min(1,abs(x.delta)),x.confidence,cycle,x.lineage_id,config.initial_retrievability))
    allowed=set(config.social_delivery_statuses)
    for x in social.records:
        require_not_future(x.status_at,as_of=social.as_of_time,label="social delivery")
        if x.status in allowed:
            fp=content_hash({"message":x.message_id,"receiver":x.receiver_person_id,"status":x.status.value})
            result.append(_new_item(x.receiver_person_id,MemoryType.SOCIAL,f"social_message:{x.message_id}",fp,(x.message_id,),
                x.evidence_refs,x.status_at,.6,.8,cycle,x.lineage_id,config.initial_retrievability))
    for x in persons.records:
        if x.state_change_summary:
            s=x.state_change_summary; require_not_future(s.changed_at,as_of=persons.as_of_time,label="state change")
            fp=content_hash({"person":x.person_id,"change":s.change_id,"content":s.content_ref})
            result.append(_new_item(x.person_id,MemoryType.EPISODIC,s.content_ref,fp,s.source_event_ids,s.evidence_refs,s.changed_at,
                s.change_magnitude,.8,cycle,s.lineage_id,config.initial_retrievability))
    for x in feedback.items:
        if x.status==FeedbackStatus.MATURED:
            require_not_future(x.matured_at,as_of=feedback.as_of_time,label="feedback")
            if config.feedback_requires_commit_hash and not x.commit_hash: raise S26ContractError("matured feedback requires commit_hash")
            fp=content_hash({"feedback":x.feedback_id,"commitment":x.commitment_id,"alignment":x.outcome_alignment})
            result.append(_new_item(x.observer_person_id,MemoryType.BELIEF_FEEDBACK,f"belief_feedback:{x.feedback_id}",fp,
                (x.feedback_id,x.commitment_id),x.evidence_refs,x.matured_at,abs(x.outcome_alignment),x.reliability,cycle,x.lineage_id,
                config.initial_retrievability))
    unknown=sorted({x.person_id for x in result}-known)
    if unknown: raise S26ContractError(f"memory candidates reference unknown people: {unknown}")
    return result

def _decay(item: MemoryItem, config: MemoryConsolidationConfig, cycle: int)->MemoryItem:
    if item.protected_audit or item.status!=MemoryStatus.ACTIVE: return item
    retr=clamp(item.retrievability-config.decay_per_cycle,0,1); status=item.status
    if cycle-item.valid_from_cycle>=config.expiration_cycles and retr<=config.expiration_retrievability_threshold: status=MemoryStatus.EXPIRED
    return item.model_copy(update={"retrievability":retr,"status":status})

def _reinforce(old: MemoryItem, new: MemoryItem, config: MemoryConsolidationConfig)->MemoryItem:
    conf=clamp(old.confidence+config.reinforcement_learning_rate*(new.confidence-old.confidence),0,1)
    retr=clamp(old.retrievability+min(config.max_retrievability_delta,new.importance*config.max_retrievability_delta),0,1)
    return old.model_copy(update={"importance":max(old.importance,new.importance),"confidence":conf,"retrievability":retr,
        "source_event_ids":tuple(sorted(set(old.source_event_ids+new.source_event_ids))),"evidence_refs":tuple(sorted(set(old.evidence_refs+new.evidence_refs))),
        "lineage_ids":tuple(sorted(set(old.lineage_ids+new.lineage_ids))),"status":MemoryStatus.ACTIVE,
        "reinforcement_count":old.reinforcement_count+1,"last_reinforced_at":new.available_at})

def consolidate_memory(**raw)->tuple[NextMemoryState,MemoryTriggerEventPanel]:
    memory=CurrentMemoryState.model_validate(raw["current_memory_state"]); trajectories=PersonLearningTrajectoryBundle.model_validate(raw["person_learning_trajectory_bundle"])
    beliefs=NextBeliefStatePanel.model_validate(raw["next_belief_state_panel"]); persons=ValidatedNextPersonStatePanel.model_validate(raw["validated_next_person_state_panel"])
    social=SocialDeliveryPanel.model_validate(raw["social_delivery_panel"]); feedback=ActiveBeliefFeedbackBundle.model_validate(raw["active_belief_feedback_bundle"])
    patch=ActiveRetroPolicyPatch.model_validate(raw["active_retro_policy_patch"]); config=MemoryConsolidationConfig.model_validate(raw["memory_consolidation_config"])
    require_same_context(memory,trajectories,beliefs,persons,social,feedback); config=_patch(config,patch,memory.cycle_id)
    items={x.memory_id:_decay(x,config,memory.cycle_id) for x in memory.items}; changed=[]; counts=defaultdict(int)
    for candidate in sorted(_candidates(trajectories,beliefs,persons,social,feedback,config),key=lambda x:(x.person_id,x.memory_type.value,x.memory_id)):
        if candidate.memory_id in items:
            item=_reinforce(items[candidate.memory_id],candidate,config); counts["reinforced"]+=1; reason=TriggerReason.REINFORCED_MEMORY
        else:
            item=candidate; counts["created"]+=1; reason=TriggerReason.NEW_MEMORY
        items[item.memory_id]=item; changed.append((item,reason))
        if item.memory_type==MemoryType.EPISODIC and item.reinforcement_count>=config.episodic_to_semantic_min_repetitions:
            items[item.memory_id]=item.model_copy(update={"status":MemoryStatus.SUPERSEDED})
            semantic=item.model_copy(update={"memory_id":derived_id("mem",item.person_id,"SEMANTIC",item.content_fingerprint),"memory_type":MemoryType.SEMANTIC,
                "supersedes_memory_id":item.memory_id,"status":MemoryStatus.ACTIVE,"valid_from_cycle":memory.cycle_id+1})
            items[semantic.memory_id]=semantic; changed.append((semantic,TriggerReason.PROMOTED_MEMORY)); counts["promoted"]+=1
    counts["expired"]=sum(x.status==MemoryStatus.EXPIRED for x in items.values())
    line=lineage_id(MODULE_ID,"next_memory_state",(memory.lineage_id,trajectories.lineage_id,beliefs.lineage_id,persons.lineage_id,social.lineage_id,feedback.lineage_id,patch.lineage_id))
    ordered=tuple(sorted(items.values(),key=lambda x:(x.person_id,x.memory_type.value,x.memory_id)))
    payload={"schema_version":"p3.s26.next_memory_state.v2","run_id":memory.run_id,"cycle_id":memory.cycle_id,"as_of_time":memory.as_of_time,"lineage_id":line,
        "memory_state_id":derived_id("memstate",memory.run_id,memory.cycle_id+1,line),"source_memory_state_id":memory.memory_state_id,"items":ordered,
        "created_count":counts["created"],"reinforced_count":counts["reinforced"],"promoted_count":counts["promoted"],"expired_count":counts["expired"]}
    state=NextMemoryState(**payload,content_hash=content_hash(payload)); trigger_line=lineage_id(MODULE_ID,"memory_trigger_event_panel",(line,)); triggers=[]
    for item,reason in changed:
        score=item.importance*item.confidence*item.retrievability
        if score>=config.memory_trigger_threshold:
            triggers.append(MemoryTriggerEvent(event_id=derived_id("memtrg",item.memory_id,reason.value,memory.cycle_id),person_id=item.person_id,memory_id=item.memory_id,
                source_event_id=item.source_event_ids[0],causal_parent_id=item.source_event_ids[0],subject=item.content_ref,created_at=item.last_reinforced_at or item.available_at,
                available_at=item.last_reinforced_at or item.available_at,created_cycle=memory.cycle_id,target_cycle=memory.cycle_id+1,trigger_score=score,reason=reason,
                evidence_refs=item.evidence_refs,lineage_id=trigger_line))
    panel=MemoryTriggerEventPanel(schema_version="p3.s26.memory_trigger_event_panel.v2",run_id=memory.run_id,cycle_id=memory.cycle_id,
        as_of_time=memory.as_of_time,lineage_id=trigger_line,records=tuple(sorted(triggers,key=lambda x:(x.person_id,x.memory_id))))
    log_event("module_succeeded",module_id=MODULE_ID,run_id=memory.run_id,cycle_id=memory.cycle_id,status="PASS",output_record_count=len(state.items))
    return state,panel
