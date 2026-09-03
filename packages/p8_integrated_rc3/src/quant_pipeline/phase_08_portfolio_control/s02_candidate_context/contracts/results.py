
"""Module result contracts."""

from quant_pipeline.phase_08_contracts.common import ModuleReceipt
from quant_pipeline.phase_08_contracts.base import StrictModel

from .bundle import P8CandidateContextBundleV1
from .equivalence import ExactEquivalenceGroupPanel, SoftSimilarityRequestPanel
from .graph import StructuralExposureGraph
from .intent import NormalizedCandidateIntentPanel
from .netting import NettingTransform
from .preferences import OrdinalPreferenceConstraintSet
from .universe import StaticAdmissibleActionUniverse


class M01Result(StrictModel):
    normalized_intents: NormalizedCandidateIntentPanel
    receipt: ModuleReceipt


class M02Result(StrictModel):
    exposure_graph: StructuralExposureGraph
    receipt: ModuleReceipt


class M03Result(StrictModel):
    equivalence_groups: ExactEquivalenceGroupPanel
    soft_similarity_requests: SoftSimilarityRequestPanel
    receipt: ModuleReceipt


class M04Result(StrictModel):
    netting_transform: NettingTransform
    receipt: ModuleReceipt


class M05Result(StrictModel):
    static_action_universe: StaticAdmissibleActionUniverse
    receipt: ModuleReceipt


class M06Result(StrictModel):
    ordinal_preferences: OrdinalPreferenceConstraintSet
    receipt: ModuleReceipt


class S2OutputResult(StrictModel):
    bundle: P8CandidateContextBundleV1
    receipt: ModuleReceipt
