from __future__ import annotations

from typing import Protocol
import numpy as np

class Ranker(Protocol):
    implementation_id: str
    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        query_ids: list[str],
        candidate_ids: list[str],
    ) -> dict[str, object]: ...
    def predict(self, features: np.ndarray, state: dict[str, object]) -> np.ndarray: ...

class RuntimeRanker(Protocol):
    implementation_id: str
    def predict(self, features: np.ndarray, state: dict[str, object]) -> np.ndarray: ...
