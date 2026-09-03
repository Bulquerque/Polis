from pathlib import Path


def test_source_of_truth_exists():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'source_of_truth' / 'standards' / 'CODE_STANDARDS.md').exists()
    assert (root / 'source_of_truth' / 'standards' / 'SEARCH_FIRST_PATCH_ONLY_POLICY.md').exists()
