from __future__ import annotations
from ..s8.artifacts import ArtifactEnvelope, ExecutionContext
from ..s8.quality import build_quality_outputs
from ..s8.validation import reject_forbidden, require_artifacts

def run_module(inputs: dict[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    require_artifacts(inputs,("underlying_feature_factors_pca","underlying_feature_embeddings","pca_fit_state_manifest","encoder_fit_state_manifest","representation_fold_plan"))
    reject_forbidden({name:item.model_dump(mode="json") for name,item in inputs.items()})
    return build_quality_outputs(inputs["pca_fit_state_manifest"],inputs["encoder_fit_state_manifest"],inputs["underlying_feature_factors_pca"],inputs["underlying_feature_embeddings"],context)
