from __future__ import annotations
from typing import Any
from .artifacts import ArtifactEnvelope
from .errors import S8Error
from .records import RepresentationPolicy

FORBIDDEN_FIELDS = {"target", "label", "future_return", "future_volatility", "prediction", "signal_direction", "candidate_id", "pnl", "sharpe"}

def require_artifacts(inputs: dict[str, ArtifactEnvelope], names: tuple[str, ...]) -> None:
    missing = [name for name in names if name not in inputs]
    if missing:
        raise S8Error("P4_S8_INPUT_INVALID", f"missing artifacts: {missing}")
    selected = [inputs[name] for name in names]
    reference = selected[0]
    for name, artifact in zip(names, selected, strict=True):
        artifact.validate_payload()
        if artifact.artifact_name != name:
            raise S8Error("P4_S8_ARTIFACT_NAME_MISMATCH", f"key={name} artifact={artifact.artifact_name}")
        if (artifact.run_id, artifact.cycle_id, artifact.as_of_time) != (reference.run_id, reference.cycle_id, reference.as_of_time):
            raise S8Error("P4_S8_CYCLE_MISMATCH", f"artifact {name} is from another run/cycle/as_of")

def validate_transform_state_coverage(matrix: ArtifactEnvelope, manifest: ArtifactEnvelope) -> None:
    catalog = matrix.metadata.get("feature_catalog", {})
    expected = {(str(item["horizon_group"]), str(item["feature_id"])) for item in catalog.values()}
    actual = {(str(item["horizon_group"]), str(item["feature_id"])) for item in manifest.records
              if str(item.get("selection_decision")) in {"KEEP", "KEEP_AS_PROXY"}}
    missing = sorted(expected - actual)
    if missing:
        raise S8Error("P4_S8_TRANSFORM_STATE_MISSING", f"selected features without transform state: {missing}")

def reject_forbidden(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_FIELDS:
                raise S8Error("P4_S8_FORBIDDEN_FIELD", f"{path}.{key}")
            reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_forbidden(child, f"{path}[{index}]")

def parse_policy(artifact: ArtifactEnvelope) -> RepresentationPolicy:
    if artifact.record_count != 1:
        raise S8Error("P4_S8_POLICY_INVALID", "representation policy must contain exactly one record")
    return RepresentationPolicy.model_validate(artifact.records[0])
