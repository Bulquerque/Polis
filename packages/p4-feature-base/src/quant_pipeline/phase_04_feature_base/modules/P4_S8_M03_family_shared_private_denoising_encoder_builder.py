from __future__ import annotations
from ..s8.artifacts import ArtifactEnvelope, ExecutionContext
from ..s8.encoder_builder import build_encoder_representations
from ..s8.validation import parse_policy, reject_forbidden, require_artifacts, validate_transform_state_coverage

def run_module(inputs: dict[str, ArtifactEnvelope], context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    require_artifacts(inputs,("underlying_feature_matrix_selected","feature_transform_state_manifest","representation_fold_plan","encoder_hyperparameter_search_plan","encoder_execution_decision","representation_policy_registry"))
    reject_forbidden({name:item.model_dump(mode="json") for name,item in inputs.items()})
    validate_transform_state_coverage(inputs["underlying_feature_matrix_selected"], inputs["feature_transform_state_manifest"])
    return build_encoder_representations(inputs["underlying_feature_matrix_selected"],inputs["representation_fold_plan"],inputs["encoder_execution_decision"],parse_policy(inputs["representation_policy_registry"]),context)
