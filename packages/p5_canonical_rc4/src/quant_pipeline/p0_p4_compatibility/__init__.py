"""Cross-phase P0–P4 compatibility adapters shipped with P5."""
from .data_projection import (
    adapt_p4_feature_matrix_for_p5, adapt_p4_research_for_p5, build_p5_outcome_bundle_from_p4,
)
from .temporal_policy import install_p5_5d_evidence_compatibility
from .publication_runner import run_live_p5_publication

__all__ = [
    "adapt_p4_feature_matrix_for_p5", "adapt_p4_research_for_p5",
    "build_p5_outcome_bundle_from_p4", "install_p5_5d_evidence_compatibility",
    "run_live_p5_publication",
]
