from __future__ import annotations

from quant_pipeline.phase_09.subphases.s09_competition_promotion import __version__ as s9_version
from quant_pipeline.phase_09.subphases.s10_memory_release import __version__ as s10_version
from quant_pipeline.phase_09.subphases.s10_memory_release.models import S10InputBundle

from tests.s10.conftest import valid_s10_input


def test_exact_s9_contract_version() -> None:
    assert s9_version == "0.1.0rc1"
    assert s10_version == "0.1.0rc1"
    inputs = valid_s10_input()
    assert inputs.build_environment.s9_distribution_version == s9_version


def test_s10_input_serializes_s9_envelope_without_copy_contract() -> None:
    inputs = valid_s10_input()
    restored = S10InputBundle.model_validate_json(inputs.model_dump_json())
    assert restored.s9_execution_envelope == inputs.s9_execution_envelope
