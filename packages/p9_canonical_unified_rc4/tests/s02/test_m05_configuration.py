from __future__ import annotations

import json

from datetime import UTC, datetime

from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner


def run(s2_request):
    return S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(s2_request)


def test_random_catalog_is_deterministic(s2_request) -> None:
    first = run(s2_request).s2_outputs.configuration_catalog
    second = run(s2_request).s2_outputs.configuration_catalog
    assert first == second
    assert len(first.configurations) == 6


def test_code_hash_change_changes_configuration_ids(s2_request) -> None:
    first = run(s2_request).s2_outputs.configuration_catalog
    raw = s2_request.model_dump(mode="json")
    raw["identity_context"]["code_artifact"]["content_sha256"] = "f" * 64
    changed = run(type(s2_request).model_validate_json(json.dumps(raw))).s2_outputs.configuration_catalog
    assert {c.configuration_id for c in first.configurations}.isdisjoint({c.configuration_id for c in changed.configurations})


def test_only_active_parameters_are_stored(result) -> None:
    catalog = result.s2_outputs.configuration_catalog
    for config in catalog.configurations:
        values = {a.parameter_id: a.value for a in config.assignments}
        opt_type = values["P8.optimizer.type"]
        assert ("P8.optimizer.cvar_alpha" in values) is (opt_type == "CVAR")
        assert ("P8.optimizer.robust_radius" in values) is (opt_type == "ROBUST")


def test_configuration_ids_are_unique(result) -> None:
    ids = [c.configuration_id for c in result.s2_outputs.configuration_catalog.configurations]
    assert len(ids) == len(set(ids))
