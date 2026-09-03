"""Canonical public contracts for P3 runtime.

Models are split by boundary domain but re-exported here to keep one stable import path.
"""

from .base import (
    StrictModel,
    ArtifactStatus,
    ExecutionMode,
    BeliefDirection,
    SocialLifecycle,
    LineageRecord,
    CanonicalArtifact,
)

from .context import (
    EvidenceRecord,
    RetrievalEvidenceMap,
    ContextSection,
    PersonContextRecord,
    PersonContextBundle,
    StimulusRecord,
    StimulusPanel,
    ActivationRecord,
    ActivationPanel,
    LearningTrajectoryRecord,
    LearningTrajectoryBundle,
)

from .cognition import (
    BeliefUpdateRecord,
    BeliefUpdatePanel,
    BeliefCommitmentRecord,
    BeliefCommitmentLog,
    PersonStateDeltaRecord,
    PersonStateDeltaPanel,
    SocialDeliveryObservation,
    SocialObservationPanel,
)

from .society import (
    BeliefDistributionRecord,
    BeliefDistributionPanel,
    SocietyStateRecord,
    SocietyStatePanel,
    MemoryFeatureRecord,
    MemoryFeatureProjection,
)

__all__ = [
    "StrictModel",
    "ArtifactStatus",
    "ExecutionMode",
    "BeliefDirection",
    "SocialLifecycle",
    "LineageRecord",
    "CanonicalArtifact",
    "EvidenceRecord",
    "RetrievalEvidenceMap",
    "ContextSection",
    "PersonContextRecord",
    "PersonContextBundle",
    "StimulusRecord",
    "StimulusPanel",
    "ActivationRecord",
    "ActivationPanel",
    "LearningTrajectoryRecord",
    "LearningTrajectoryBundle",
    "BeliefUpdateRecord",
    "BeliefUpdatePanel",
    "BeliefCommitmentRecord",
    "BeliefCommitmentLog",
    "PersonStateDeltaRecord",
    "PersonStateDeltaPanel",
    "SocialDeliveryObservation",
    "SocialObservationPanel",
    "BeliefDistributionRecord",
    "BeliefDistributionPanel",
    "SocietyStateRecord",
    "SocietyStatePanel",
    "MemoryFeatureRecord",
    "MemoryFeatureProjection",
]
