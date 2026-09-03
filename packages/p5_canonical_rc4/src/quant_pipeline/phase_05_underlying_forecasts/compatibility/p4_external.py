"""Public P5 facade for the cross-phase P0–P4 compatibility package."""
from quant_pipeline.p0_p4_compatibility import (
    adapt_p4_feature_matrix_for_p5,
    adapt_p4_research_for_p5,
    build_p5_outcome_bundle_from_p4,
    install_p5_5d_evidence_compatibility,
    run_live_p5_publication,
)

__all__ = [
    "adapt_p4_feature_matrix_for_p5",
    "adapt_p4_research_for_p5",
    "build_p5_outcome_bundle_from_p4",
    "install_p5_5d_evidence_compatibility",
    "run_live_p5_publication",
]
