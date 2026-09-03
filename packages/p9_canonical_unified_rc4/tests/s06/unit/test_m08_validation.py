from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.runner import run_s6


def test_validation_is_explicit_about_specialist_limitations(full_request):
    request = full_request.model_copy(update={"evt": None, "dro": None})
    result = run_s6(request)
    assert result.validation.status in {
        S6State.VALIDATED_WITH_LIMITATIONS,
        S6State.MODEL_NOT_FIT_FOR_STRESS,
    }
    assert any("EVT" in limitation or "DRO" in limitation for limitation in result.validation.limitations)


def test_all_module_receipts_are_conserved(full_request):
    result = run_s6(full_request)
    assert {receipt.module_id for receipt in result.module_receipts} == {
        f"P9.S6.M0{i}" for i in range(1, 9)
    }
