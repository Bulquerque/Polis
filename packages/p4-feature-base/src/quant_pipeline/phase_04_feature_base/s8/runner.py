from __future__ import annotations
import json, sys
from pathlib import Path
from pydantic import TypeAdapter
from ..modules.P4_S8_M01_representation_fold_hyperparameter_controller import run_module as m01
from ..modules.P4_S8_M02_family_pca_sparse_pca_builder import run_module as m02
from ..modules.P4_S8_M03_family_shared_private_denoising_encoder_builder import run_module as m03
from ..modules.P4_S8_M04_representation_quality_horizon_packager import run_module as m04
from .artifacts import ArtifactEnvelope, ExecutionContext

MODULE_SEQUENCE=(m01,m02,m03,m04)
OUTPUTS={"representation_fold_plan","encoder_hyperparameter_search_plan","encoder_execution_decision","underlying_feature_factors_pca","pca_fit_state_manifest","underlying_feature_embeddings","encoder_fit_state_manifest","representation_quality_report","representation_horizon_bundle","encoder_hyperparameter_search_report"}

def run_subphase(inputs: dict[str,ArtifactEnvelope], context: ExecutionContext) -> dict[str,ArtifactEnvelope]:
    artifacts=dict(inputs)
    for module in MODULE_SEQUENCE:
        artifacts.update(module(artifacts,context))
    return {name:artifacts[name] for name in sorted(OUTPUTS)}

def main() -> int:
    if len(sys.argv)!=2:
        print("usage: python -m quant_pipeline.phase_04_feature_base.s8.runner INPUT.json")
        return 2
    payload=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    context=ExecutionContext.model_validate(payload["context"])
    inputs=TypeAdapter(dict[str,ArtifactEnvelope]).validate_python(payload["inputs"])
    outputs=run_subphase(inputs,context)
    print(json.dumps({name:value.model_dump(mode="json") for name,value in outputs.items()},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
