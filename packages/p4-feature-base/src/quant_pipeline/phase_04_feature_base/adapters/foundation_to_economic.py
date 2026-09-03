from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from importlib.resources import files
from typing import Any

import yaml

from ..economic_models import ObserverExecutionRegistry
from ..runtime.canonical import deterministic_id
from .canonical_projection import canonical_panel_for_economic

_ATOMIC_MODULES = {
    "price.": "P4.S4.M01",
    "liquidity.": "P4.S4.M02",
    "risk.": "P4.S4.M03",
    "cross_asset.": "P4.S4.M04",
    "options.": "P4.S4.M05",
    "macro.": "P4.S4.M06",
    "event.": "P4.S4.M06",
    "calendar.": "P4.S4.M06",
    "social.": "P4.S4.M07",
    "fundamental.": "P4.S4.M08",
}


def _economic_registry_template() -> dict[str, Any]:
    resource = files("quant_pipeline.phase_04_feature_base._resources.registries_economic").joinpath(
        "DEFAULT_APPROVED_HYPOTHESIS_PASSPORT_REGISTRY.yaml"
    )
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def _module_for_atomic(feature_id: str) -> str | None:
    for prefix, module_id in _ATOMIC_MODULES.items():
        if feature_id.startswith(prefix):
            return module_id
    return None


def _atomic_observer_for_feature(feature_id: str) -> tuple[str, str, dict[str, Any]]:
    """Resolve a required atomic feature into its executable observer specification.

    The economic hypothesis registry names *output features*. Some atomic factories use a
    generic observer to materialize many source-specific outputs (macro levels/changes and
    narrative shifts). The resolver keeps that distinction explicit instead of pretending
    that every output feature is itself an operator implementation.
    """
    if feature_id == "risk.realized_volatility_5":
        return "risk.realized_volatility", feature_id, {"window": 5}
    for base in ("macro.level", "macro.change_1", "macro.acceleration"):
        if feature_id == base or feature_id.startswith(f"{base}."):
            return base, base, {}
    if feature_id == "social.narrative_shift" or feature_id.startswith("social.narrative_shift."):
        return "social.narrative_shift", "social.narrative_shift", {}
    return feature_id, feature_id, {}


def _approved_hypothesis_ids(approved_hypotheses: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("hypothesis_id"))
        for row in approved_hypotheses.get("records", [])
        if str(row.get("status", "APPROVED")) not in {"REJECTED", "BLOCKED", "DISABLED"}
    }


def _required_atomic_features(template: Mapping[str, Any], approved_ids: set[str]) -> set[str]:
    features: set[str] = set()
    for row in template.get("records", []):
        if str(row.get("hypothesis_id")) in approved_ids and row.get("enabled", True):
            features.update(str(item) for item in row.get("source_feature_ids", []))
    return features


def _atomic_record(required_feature_id: str) -> dict[str, Any] | None:
    module_id = _module_for_atomic(required_feature_id)
    if module_id is None:
        return None
    observer_id, output_feature_id, parameters = _atomic_observer_for_feature(required_feature_id)
    return {
        "observer_id": observer_id,
        "module_id": module_id,
        "feature_id": output_feature_id,
        "parameterization_id": f"{required_feature_id}.primary",
        "horizon_group": "MEDIUM",
        "enabled": True,
        "parameters": parameters,
    }


def _apply_default_windows(records: list[dict[str, Any]]) -> None:
    defaults = {
        "liquidity.relative_volume": 21,
        "liquidity.amihud": 21,
        "liquidity.stale_frequency": 21,
        "risk.realized_volatility": 21,
        "risk.downside_semivariance": 21,
        "risk.drawdown": 63,
        "risk.drawdown_duration": 63,
        "risk.skewness": 63,
        "risk.kurtosis": 63,
        "risk.vol_of_vol": 21,
        "cross_asset.beta": 63,
        "cross_asset.correlation": 63,
        "cross_asset.residual_return": 63,
    }
    for row in records:
        if row["observer_id"] in defaults and "window" not in row["parameters"]:
            row["parameters"]["window"] = defaults[row["observer_id"]]


def compile_atomic_execution_registry(
    approved_hypotheses: Mapping[str, Any], *, run_id: str, cycle_id: str,
    as_of_time: datetime, pipeline_version: str,
) -> dict[str, Any]:
    """Compile S3-approved hypotheses into executable S4 atomic specifications."""
    template = _economic_registry_template()
    atomic_ids = _required_atomic_features(template, _approved_hypothesis_ids(approved_hypotheses))
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for feature_id in sorted(atomic_ids):
        row = _atomic_record(feature_id)
        if row is None:
            continue
        key = (row["module_id"], row["observer_id"], row["feature_id"])
        if key not in seen:
            seen.add(key)
            records.append(row)
    _apply_default_windows(records)
    payload = {
        "artifact_id": deterministic_id("atomic-execution-registry", records, 24),
        "schema_version": "p4.atomic.execution.v1",
        "pipeline_version": pipeline_version,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_of_time,
        "lineage_id": deterministic_id(
            "lineage-atomic-registry", [approved_hypotheses.get("lineage_id"), records], 28
        ),
        "records": records,
    }
    return ObserverExecutionRegistry.model_validate(payload).model_dump(mode="json")


def economic_hypothesis_registry(
    approved_hypotheses: Mapping[str, Any], *, run_id: str, cycle_id: str, as_of_time: datetime,
    pipeline_version: str,
) -> dict[str, Any]:
    """Filter the S5 registry using S3-approved hypothesis IDs and bind it to the active context."""
    approved_ids = _approved_hypothesis_ids(approved_hypotheses)
    template = _economic_registry_template()
    records = [row for row in template.get("records", []) if row.get("hypothesis_id") in approved_ids]
    return {
        **template,
        "artifact_id": deterministic_id("economic-hypothesis-registry", records, 24),
        "pipeline_version": pipeline_version,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "as_of_time": as_of_time.isoformat(),
        "lineage_id": deterministic_id("lineage-economic-hypotheses", [approved_hypotheses.get("lineage_id"), records], 28),
        "records": records,
    }
