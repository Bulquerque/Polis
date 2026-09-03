"""Legacy import alias for the frozen P2->P4 compatibility surface.

The V14.9 canonical module is ``phase2_handoff_validator``.  Older P2
boundary tests and consumers used ``phase2_feature_intake_validator``; keeping
this thin alias preserves import compatibility without creating a second
implementation or contract.
"""

from .P4_S1_M01_phase2_handoff_validator import (  # noqa: F401
    MODULE_ID,
    MODULE_NAME,
    REQUIRED_INPUTS,
    execute,
    run_module,
)

_canonical_run_module = run_module


def run_module(inputs, config=None):
    """Run the canonical validator and expose the historical output alias.

    The alias is deliberately provenance-backed and is not consumed by the
    V14.9 integrated runner.  It exists for frozen P2/P6 boundary callers that
    still assert the RC4.1 name ``validated_phase2_feature_inputs``.
    """
    result = _canonical_run_module(inputs, config)
    bundle = result["outputs"]["validated_phase2_bundle"]
    # The canonical boundary returns JSON-shaped mappings.  Keep the legacy
    # alias lossless across both mapping and model-shaped callers.
    if isinstance(bundle, dict):
        created_at = bundle.get("created_at")
        artifact_id = bundle.get("artifact_id")
    else:
        created_at = getattr(bundle, "created_at", None)
        artifact_id = getattr(bundle, "artifact_id", None)
    result["outputs"]["validated_phase2_feature_inputs"] = {
        "available_at_preserved": True,
        "source_artifact_name": "validated_phase2_bundle",
        "source_path": "phase_04_extracted/phase_04_feature_base_agent_package_RC4_1/src/quant_pipeline/phase_04_feature_base/modules/P4_S1_M01_phase2_handoff_validator.py",
        "generated_by": "P4.S1.M01.phase2_handoff_validator",
        "generated_at": str(created_at),
        "requirements_covered": ["P4.S1.M01", "P2.S6.M02->P4.S1.M01"],
        "validation_result": "PASS",
        "canonical_filename": "validated_phase2_bundle",
        "canonical_artifact_id": artifact_id,
    }
    return result

__all__ = ["MODULE_ID", "MODULE_NAME", "REQUIRED_INPUTS", "execute", "run_module"]
