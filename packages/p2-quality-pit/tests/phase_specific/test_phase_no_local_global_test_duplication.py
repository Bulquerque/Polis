from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_global_structural_tests_copied_locally():
    forbidden_names = {
        'test_rc3_documentation_and_diagrams.py',
        'test_rc4_phase0_reporting.py',
        'test_no_tbd_markers.py',
        'test_global_structure_policy.py',
    }
    local_tests = {p.name for p in (ROOT / 'tests').rglob('test_*.py')}
    assert not (local_tests & forbidden_names)
