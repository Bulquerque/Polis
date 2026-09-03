
"""Export Draft 2020-12 schemas from S2 canonical Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts.bundle import P8CandidateContextBundleV1, S2InputBundleV1
from .contracts.equivalence import ExactEquivalenceGroupPanel, SoftSimilarityRequestPanel
from .contracts.graph import StructuralExposureGraph
from .contracts.intent import NormalizedCandidateIntentPanel
from .contracts.netting import NettingTransform
from .contracts.preferences import OrdinalPreferenceConstraintSet
from .contracts.universe import StaticAdmissibleActionUniverse

_MODELS = {
    "P8_S2_INPUT_BUNDLE_V1.schema.json": S2InputBundleV1,
    "P8_NORMALIZED_CANDIDATE_INTENT_PANEL_V1.schema.json": NormalizedCandidateIntentPanel,
    "P8_STRUCTURAL_EXPOSURE_GRAPH_V1.schema.json": StructuralExposureGraph,
    "P8_EXACT_EQUIVALENCE_GROUP_PANEL_V1.schema.json": ExactEquivalenceGroupPanel,
    "P8_SOFT_SIMILARITY_REQUEST_PANEL_V1.schema.json": SoftSimilarityRequestPanel,
    "P8_NETTING_TRANSFORM_V1.schema.json": NettingTransform,
    "P8_STATIC_ADMISSIBLE_ACTION_UNIVERSE_V1.schema.json": StaticAdmissibleActionUniverse,
    "P8_ORDINAL_PREFERENCE_CONSTRAINT_SET_V1.schema.json": OrdinalPreferenceConstraintSet,
    "P8_CANDIDATE_CONTEXT_BUNDLE_V1.schema.json": P8CandidateContextBundleV1,
}


def export_schemas(target: Path) -> tuple[Path, ...]:
    target.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, model in _MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = filename
        path = target / filename
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(path)
    return tuple(paths)
