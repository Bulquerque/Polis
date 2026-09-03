from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
import numpy as np

@dataclass(frozen=True, slots=True)
class DeclarativeLinearRanker:
    """Inference-only adapter for frozen linear LTR artifacts."""

    implementation_id: str

    def predict(self, features: np.ndarray, state: Mapping[str, object]) -> np.ndarray:
        medians = np.asarray(state["imputation_medians"], dtype=float)
        means = np.asarray(state["feature_means"], dtype=float)
        scales = np.asarray(state["feature_scales"], dtype=float)
        coefficients = np.asarray(state["coefficients"], dtype=float)
        filled = np.where(np.isnan(features), medians, features)
        standardized = (filled - means) / scales
        return standardized @ coefficients + float(state.get("intercept", 0.0))
