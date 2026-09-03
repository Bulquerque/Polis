from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus,
    BeliefValueType,
    DirectionalBeliefPayload,
    LineageRecord,
    StructuredBeliefProposalRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s22_models import (
    BeliefDelta,
    BeliefValidationStatus,
    BoundEvidenceRecord,
    CurrentBeliefStatePanel,
    CurrentBeliefStateRecord,
    EvidenceBindingStatus,
    EvidenceBoundBeliefUpdatePanel,
    EvidenceBoundBeliefUpdateRecord,
    EvidenceRelation,
    EvidenceSourceType,
    ValidatedBeliefUpdateRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s23_models import (
    CurrentPersonStatePanel,
    CurrentPersonStateRecord,
    PersonSchemaPolicy,
    PersonStateIdentity,
    StateChangeConfig,
)

UTC=timezone.utc
T0=datetime(2026,1,1,tzinfo=UTC)
T1=T0+timedelta(days=31)


def lineage(name: str, producer: str='fixture')->LineageRecord:
    return LineageRecord(lineage_id=f'lin-{name}',source_artifact_ids=(name,),producer_module_id=producer)


def current_person_panel() -> CurrentPersonStatePanel:
    record=CurrentPersonStateRecord(
        person_state_id='ps-1',person_id='person-1',profile_hash='profile-hash-1',
        identity=PersonStateIdentity(life_stage_at_creation='young_adult',creator_provenance={'creator_run_id':'run-create-1'}),
        core_personality={'curiosity':0.7},cognitive_capacity={'reasoning':0.8},knowledge={'directional_outlook':0.2},
        trust={'general':0.5},tool_proficiency={'research':0.3},attention={'information_focus':0.4},
        confidence={'current':0.4},functional_affect={'uncertainty_pressure':0.6},belief_refs=('belief-old',),
        updated_at=T0,state_version=1,
    )
    return CurrentPersonStatePanel(status=ArtifactStatus.READY,records=(record,),lineage=lineage('person-state'))


def current_belief_panel() -> CurrentBeliefStatePanel:
    rec=CurrentBeliefStateRecord(
        belief_state_id='belief-old',person_id='person-1',underlying_id='PETR4',proposition_id='directional_outlook',horizon='21d',
        payload=DirectionalBeliefPayload(value_type=BeliefValueType.DIRECTIONAL_SCORE,direction='BULLISH',score=0.1),confidence=0.4,uncertainty=0.6,evidence_refs=('ev-old',),updated_at=T0,state_version=1,
    )
    return CurrentBeliefStatePanel(status=ArtifactStatus.READY,records=(rec,),lineage=lineage('belief-state'))


def bound_updates(*, confidence:float=0.8, uncertainty:float=0.2, bound_at=T1, binding=EvidenceBindingStatus.BOUND) -> EvidenceBoundBeliefUpdatePanel:
    proposal=StructuredBeliefProposalRecord(
        belief_proposal_id='proposal-1',cognition_transaction_id='tx-1',person_id='person-1',underlying_id='PETR4',
        proposition_id='directional_outlook',horizon='21d',payload=DirectionalBeliefPayload(value_type=BeliefValueType.DIRECTIONAL_SCORE,direction='BULLISH',score=0.4),strength=0.7,confidence=confidence,
        uncertainty=uncertainty,supporting_evidence_refs=('ev-1',),opposing_evidence_refs=(),generated_at=bound_at,as_of=bound_at,
    )
    prior=current_belief_panel().records[0]
    delta=BeliefDelta(value_type=BeliefValueType.DIRECTIONAL_SCORE,prior_payload=prior.payload,accepted_payload=proposal.payload,scalar_delta=0.3,component_deltas={'score':0.3},distance_l1=0.3)
    validated=ValidatedBeliefUpdateRecord(
        belief_update_id='update-1',proposal=proposal,prior_state=prior,validation_status=BeliefValidationStatus.ACCEPTED,
        delta=delta,validated_at=bound_at,next_state_version=2,policy_version='s22-policy-v1',
    )
    evidence=BoundEvidenceRecord(evidence_id='ev-1',relation=EvidenceRelation.SUPPORTING,source_type=EvidenceSourceType.RETRIEVAL,source_id='source-1',available_at=bound_at-timedelta(days=1),content_hash='hash-1',source_quality=0.9)
    rec=EvidenceBoundBeliefUpdateRecord(validated_update=validated,binding_status=binding,supporting_evidence=(evidence,),evidence_coverage=1.0,mean_source_quality=0.9,bound_at=bound_at)
    return EvidenceBoundBeliefUpdatePanel(status=ArtifactStatus.READY,records=(rec,),lineage=lineage('bound-belief'))


def policy()->PersonSchemaPolicy:return PersonSchemaPolicy()
def config()->StateChangeConfig:return StateChangeConfig()
