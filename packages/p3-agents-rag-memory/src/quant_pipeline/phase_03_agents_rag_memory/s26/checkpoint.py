"""P3.S26.M03 — replay-complete cycle checkpoint."""
from __future__ import annotations
from .artifacts import *
from .common import content_hash, derived_id, lineage_id, log_event, require_same_context
from .errors import S26ContractError, S26LineageError
from .types import ArtifactStatus
MODULE_ID="P3.S26.M03"
INFO={
"validated_next_person_state_panel":("validated_next_person_state_panel.p3.s26.v2","p3.s26.validated_next_person_state_panel.v2","person_id","P3.S23.M02"),
"next_belief_state_panel":("next_belief_state_panel.p3.s26.v2","p3.s26.next_belief_state_panel.v2","person_id/underlying_id/proposition_id/horizon","P3.S23.M01"),
"next_memory_state":("next_memory_state.p3.s26.v2","p3.s26.next_memory_state.v2","memory_id","P3.S26.M01"),
"next_social_graph":("next_social_graph.p3.s25.v2","p3.s25.next_social_graph.v2","edge_id","P3.S25.M03"),
"next_cycle_endogenous_stimulus_queue":("next_cycle_endogenous_stimulus_queue.p3.s26.v2","p3.s26.next_cycle_endogenous_stimulus_queue.v2","stimulus_id","P3.S26.M02"),
"belief_outcome_commitment_log":("belief_outcome_commitment_log.p3.s26.v2","p3.s26.belief_outcome_commitment_log.v2","commitment_id","P3.S22.M03")}

def commitment_hash(x: BeliefCommitment)->str:
    return content_hash({"commitment_id":x.commitment_id,"person_id":x.person_id,"underlying_id":x.underlying_id,"proposition_id":x.proposition_id,
        "horizon":x.horizon,"belief_value":x.belief_value,"confidence":x.confidence,"uncertainty":x.uncertainty,"committed_at":x.committed_at,
        "matures_at":x.matures_at,"evidence_refs":x.evidence_refs,"lineage_id":x.lineage_id})

def _validate_log(log: BeliefOutcomeCommitmentLog,snapshot: Phase3RunSnapshot)->None:
    ids=[x.commitment_id for x in log.commitments]
    if len(ids)!=len(set(ids)): raise S26LineageError("duplicate commitment ID")
    missing=sorted((set(snapshot.prior_commitment_ids)|set(log.prior_commitment_ids))-set(ids))
    if missing: raise S26LineageError(f"append-only log missing prior IDs: {missing}")
    for x in log.commitments:
        if x.committed_at>snapshot.as_of_time: raise S26LineageError("commitment is after as_of")
        if x.commit_hash!=commitment_hash(x): raise S26LineageError(f"invalid commitment hash: {x.commitment_id}")
    payload=log.model_dump(mode="python",exclude_none=True); payload.pop("content_hash",None); expected=content_hash(payload)
    if log.content_hash!=expected: raise S26LineageError("commitment log hash mismatch")

def _hash(value)->str:
    data=value.model_dump(mode="python",exclude_none=True); provided=data.pop("content_hash",None); computed=content_hash(data)
    if provided is not None and provided!=computed: raise S26LineageError("artifact content_hash mismatch")
    return computed

def _rows(name,value)->int:
    if hasattr(value,"records"): return len(value.records)
    if hasattr(value,"items"): return len(value.items)
    if hasattr(value,"stimuli"): return len(value.stimuli)
    if hasattr(value,"commitments"): return len(value.commitments)
    raise S26ContractError(f"cannot count rows for {name}")

def _entry(name,value)->ArtifactManifestEntry:
    schema_id,version,grain,producer=INFO[name]; digest=_hash(value)
    return ArtifactManifestEntry(artifact_id=derived_id("art",name,digest),artifact_name=name,schema_id=schema_id,schema_version=version,
        content_hash=digest,row_count=_rows(name,value),grain=grain,producer_module_id=producer,lineage_id=value.lineage_id,status=ArtifactStatus.READY)

def build_cycle_checkpoint(**raw)->CycleStateSnapshotOut:
    persons=ValidatedNextPersonStatePanel.model_validate(raw["validated_next_person_state_panel"]); beliefs=NextBeliefStatePanel.model_validate(raw["next_belief_state_panel"])
    memory=NextMemoryState.model_validate(raw["next_memory_state"]); social=NextSocialGraph.model_validate(raw["next_social_graph"])
    queue=NextCycleEndogenousStimulusQueue.model_validate(raw["next_cycle_endogenous_stimulus_queue"]); snapshot=Phase3RunSnapshot.model_validate(raw["phase3_run_snapshot"])
    commitments=BeliefOutcomeCommitmentLog.model_validate(raw["belief_outcome_commitment_log"]); require_same_context(persons,beliefs,memory,social,queue,snapshot,commitments)
    if queue.source_cycle_id!=snapshot.cycle_id or queue.target_cycle_id!=snapshot.next_cycle_id: raise S26ContractError("queue cycle identity mismatch")
    _validate_log(commitments,snapshot)
    families={"validated_next_person_state_panel":persons,"next_belief_state_panel":beliefs,"next_memory_state":memory,"next_social_graph":social,
        "next_cycle_endogenous_stimulus_queue":queue,"belief_outcome_commitment_log":commitments}
    manifest=tuple(_entry(name,value) for name,value in families.items()); refs={x.artifact_name:x.artifact_id for x in manifest}
    line=lineage_id(MODULE_ID,"cycle_state_snapshot_out",tuple(x.lineage_id for x in manifest)+(snapshot.lineage_id,))
    payload={"schema_version":"p3.s26.cycle_state_snapshot_out.v2","snapshot_id":derived_id("cycleckpt",snapshot.run_id,snapshot.cycle_id,snapshot.next_cycle_id,*(x.content_hash for x in manifest)),
        "run_id":snapshot.run_id,"source_cycle_id":snapshot.cycle_id,"target_cycle_id":snapshot.next_cycle_id,"as_of_time":snapshot.as_of_time,
        "available_from_cycle":snapshot.next_cycle_id,"lineage_id":line,"person_state_ref":refs["validated_next_person_state_panel"],
        "belief_state_ref":refs["next_belief_state_panel"],"memory_state_ref":refs["next_memory_state"],"social_graph_ref":refs["next_social_graph"],
        "endogenous_stimulus_queue_ref":refs["next_cycle_endogenous_stimulus_queue"],"belief_commitment_log_ref":refs["belief_outcome_commitment_log"],
        "run_snapshot_ref":snapshot.snapshot_id,"foundation_manifest_ref":snapshot.foundation_manifest_ref,"config_manifest_ref":snapshot.config_manifest_ref,
        "prompt_manifest_ref":snapshot.prompt_manifest_ref,"model_registry_ref":snapshot.model_registry_ref,"provider_fingerprint_ref":snapshot.provider_fingerprint_ref,
        "tool_registry_ref":snapshot.tool_registry_ref,"entitlement_ref":snapshot.entitlement_ref,"rag_index_ref":snapshot.rag_index_ref,"graph_index_ref":snapshot.graph_index_ref,
        "memory_index_ref":snapshot.memory_index_ref,"replay_cache_ref":snapshot.replay_cache_ref,"artifact_manifest":manifest}
    result=CycleStateSnapshotOut(**payload,content_hash=content_hash(payload)); log_event("module_succeeded",module_id=MODULE_ID,run_id=result.run_id,cycle_id=result.source_cycle_id,status="PASS",artifact_count=len(manifest))
    return result
