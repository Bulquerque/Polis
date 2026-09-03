from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s2_temporal import (
    TEMPORAL_POLICY_VERSION,
    enforce_cutoff,
    normalize_record_temporal,
    parse_cutoff,
    quality_index,
)

_REQUIRED_INPUTS = ["raw_artifact_read_bundle", "source_quality_panel"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    require_inputs(inputs, _REQUIRED_INPUTS)

    rows = records(inputs["raw_artifact_read_bundle"], "raw_artifact_read_bundle")
    if not rows:
        raise ContractValidationError("available_at_required violation: raw_artifact_read_bundle is empty")

    quality_by_source = quality_index(inputs["source_quality_panel"])
    cutoff = parse_cutoff(config.get("as_of_date"), config)
    normalized: list[dict] = []

    for row in rows:
        normalized_row = normalize_record_temporal(row, quality_by_source, config)
        enforce_cutoff(normalized_row, cutoff)
        normalized.append(normalized_row)

    no_forbidden_rows(normalized)
    if any(not row.get("available_at") for row in normalized):
        raise ContractValidationError("available_at_required violation")

    output = artifact(
        "pit-normalized-raw-bundle",
        normalized,
        config,
        available_at_required=True,
        no_future_availability=True,
        temporal_policy_version=TEMPORAL_POLICY_VERSION,
        as_of_date_applied=cutoff is not None,
        timezone_normalized=True,
    )
    return {
        "module_id": "P2.S2.M01",
        "module_name": "temporal_availability_normalizer",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S2",
        "contract": "P2_S2_M01_temporal_availability_normalizer.yaml",
        "required_inputs": _REQUIRED_INPUTS,
        "outputs": {"pit_normalized_raw_bundle": output},
    }
