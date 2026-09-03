from quant_pipeline.phase_09.subphases.s06_structural_stress.runner import run_s6


def test_full_runner_is_byte_reproducible(full_request):
    left = run_s6(full_request).model_dump_json()
    right = run_s6(full_request).model_dump_json()
    assert left == right
