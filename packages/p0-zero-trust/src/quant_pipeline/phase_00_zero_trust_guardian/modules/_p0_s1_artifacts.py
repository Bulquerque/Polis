from __future__ import annotations

from functools import lru_cache

from ._module_executor import ContractValidationError
from ._p0_s1_common import load_yaml_mapping, package_root


CLASSIFICATION_PATH = (
    package_root() / "source_of_truth" / "architecture" / "ARTIFACT_CLASSIFICATION.yaml"
)


@lru_cache(maxsize=1)
def artifact_classes() -> dict[str, str]:
    data = load_yaml_mapping(CLASSIFICATION_PATH, "artifact classification")
    values = data.get("artifacts")
    if not isinstance(values, dict):
        raise ContractValidationError("artifact classification is malformed")
    normalized = {str(key): str(value) for key, value in values.items()}
    invalid = sorted(
        key
        for key, value in normalized.items()
        if value not in {"technical_metadata", "economic_payload"}
    )
    if invalid:
        raise ContractValidationError(
            f"artifact classification has invalid classes: {invalid[:5]}"
        )
    return normalized


def is_economic_artifact(name: str) -> bool:
    classes = artifact_classes()
    if name not in classes:
        raise ContractValidationError(
            f"artifact has no explicit architecture classification: {name}"
        )
    return classes[name] == "economic_payload"
