"""Bounded scikit-learn challengers with deterministic, integrity-checked state."""
from __future__ import annotations

import base64
import hashlib
import pickle
from typing import Any

import numpy as np
from sklearn import __version__ as sklearn_version
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor

from ..errors import TrainingError


# Pickle is intentionally constrained to state created by this interpreter.
# A digest stored beside an untrusted pickle is not an authenticity proof: an
# attacker can replace both.  Keeping the accepted digest out-of-band in
# process memory prevents externally supplied state from reaching pickle.loads.
_TRUSTED_PICKLE_HASHES: set[str] = set()


def _serialize(estimator: object, kind: str, feature_importance: list[float] | None) -> dict[str, Any]:
    payload = pickle.dumps(estimator, protocol=5)
    digest = hashlib.sha256(payload).hexdigest()
    _TRUSTED_PICKLE_HASHES.add(digest)
    return {
        "kind": kind,
        "serialization": "INTERNAL_SKLEARN_PICKLE_BASE64",
        "blob": base64.b64encode(payload).decode("ascii"),
        "blob_sha256": digest,
        "sklearn_version": sklearn_version,
        "feature_importance": feature_importance,
        "trust_boundary": "P5_INTERNAL_SAME_PROCESS_CONTENT_ADDRESSED_ONLY",
        "deserialization_policy": "SAME_PROCESS_ONLY",
    }


def _deserialize(state: dict[str, Any], expected_kind: str) -> object:
    if state.get("kind") != expected_kind:
        raise TrainingError(f"model kind differs from {expected_kind}")
    if state.get("serialization") != "INTERNAL_SKLEARN_PICKLE_BASE64":
        raise TrainingError("unsupported sklearn model serialization")
    if state.get("trust_boundary") != "P5_INTERNAL_SAME_PROCESS_CONTENT_ADDRESSED_ONLY":
        raise TrainingError("serialized sklearn model crossed its trust boundary")
    if state.get("deserialization_policy") != "SAME_PROCESS_ONLY":
        raise TrainingError("serialized sklearn model deserialization policy is invalid")
    if state.get("sklearn_version") != sklearn_version:
        raise TrainingError("serialized sklearn model sklearn version mismatch")
    try:
        payload = base64.b64decode(str(state["blob"]), validate=True)
    except (KeyError, ValueError) as exc:
        raise TrainingError("serialized sklearn model is malformed") from exc
    digest = hashlib.sha256(payload).hexdigest()
    if digest != state.get("blob_sha256"):
        raise TrainingError("serialized sklearn model integrity check failed")
    if digest not in _TRUSTED_PICKLE_HASHES:
        raise TrainingError("serialized sklearn model is not trusted in this process")
    try:
        return pickle.loads(payload)  # noqa: S301 - digest was registered out-of-band by _serialize
    except (pickle.UnpicklingError, AttributeError, EOFError, ValueError) as exc:
        raise TrainingError("serialized sklearn model cannot be restored") from exc


class HistogramGradientBoostingResolver:
    implementation_id = "builtin.histogram_gradient_boosting"

    def fit(
        self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int,
    ) -> dict[str, Any]:
        max_iter = int(parameters.get("max_iter", 40))
        max_leaf_nodes = int(parameters.get("max_leaf_nodes", 15))
        learning_rate = float(parameters.get("learning_rate", 0.05))
        if not 10 <= max_iter <= 200 or not 3 <= max_leaf_nodes <= 63:
            raise TrainingError("histogram boosting resource bounds are invalid")
        if not 0.001 <= learning_rate <= 0.5:
            raise TrainingError("histogram boosting learning_rate is invalid")
        estimator = HistGradientBoostingRegressor(
            max_iter=max_iter,
            max_leaf_nodes=max_leaf_nodes,
            learning_rate=learning_rate,
            random_state=seed,
            early_stopping=False,
            l2_regularization=float(parameters.get("l2_regularization", 0.1)),
        )
        estimator.fit(x, y)
        return _serialize(estimator, "histogram_gradient_boosting", None)

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        estimator = _deserialize(model, "histogram_gradient_boosting")
        if not isinstance(estimator, HistGradientBoostingRegressor):
            raise TrainingError("restored histogram model has unexpected type")
        return np.asarray(estimator.predict(x), dtype=float)


class ExtraTreesResolver:
    implementation_id = "builtin.extra_trees"

    def fit(
        self, x: np.ndarray, y: np.ndarray, parameters: dict[str, Any], seed: int,
    ) -> dict[str, Any]:
        estimators = int(parameters.get("n_estimators", 32))
        depth = int(parameters.get("max_depth", 6))
        leaf = int(parameters.get("min_samples_leaf", 3))
        if not 8 <= estimators <= 128 or not 2 <= depth <= 20 or leaf < 1:
            raise TrainingError("extra-trees resource bounds are invalid")
        estimator = ExtraTreesRegressor(
            n_estimators=estimators,
            max_depth=depth,
            min_samples_leaf=leaf,
            random_state=seed,
            n_jobs=1,
            bootstrap=False,
        )
        estimator.fit(x, y)
        importance = np.asarray(estimator.feature_importances_, dtype=float).tolist()
        return _serialize(estimator, "extra_trees", importance)

    def predict(self, model: dict[str, Any], x: np.ndarray) -> np.ndarray:
        estimator = _deserialize(model, "extra_trees")
        if not isinstance(estimator, ExtraTreesRegressor):
            raise TrainingError("restored extra-trees model has unexpected type")
        return np.asarray(estimator.predict(x), dtype=float)
