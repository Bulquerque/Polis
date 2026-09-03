from __future__ import annotations

from copy import deepcopy

from .s31_support import m01_inputs, run_m01


def test_society_record_order_does_not_change_output():
    inputs = m01_inputs()
    second = deepcopy(inputs["validated_society_state_panel"]["records"][0])
    second["underlying_id"] = "VALE3"
    second["lineage_id"] = "lineage-society-vale3"
    inputs["validated_society_state_panel"]["records"].append(second)
    first = run_m01(inputs)
    inputs["validated_society_state_panel"]["records"].reverse()
    second_output = run_m01(inputs)
    assert first == second_output


def test_phase4_entry_order_does_not_change_output():
    inputs = m01_inputs()
    first = run_m01(inputs)
    inputs["phase4_social_handoff_manifest"]["entries"].reverse()
    second = run_m01(inputs)
    assert first == second
