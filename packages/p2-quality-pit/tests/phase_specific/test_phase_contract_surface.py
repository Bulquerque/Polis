from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase_specific_contract_surface_exists():
    required = [
        'README.md', 'SOURCE_OF_TRUTH.md', 'PHASE_OVERVIEW.md',
        'INPUT_CONTRACTS.md', 'OUTPUT_CONTRACTS.md',
        'contracts/INPUT_CONTRACTS.yaml', 'contracts/OUTPUT_CONTRACTS.yaml',
        'contracts/MODULE_IO_MATRIX.yaml', 'contracts/SOURCE_OF_TRUTH_REFERENCES.yaml'
    ]
    missing = [item for item in required if not (ROOT / item).exists()]
    assert not missing, missing


def test_phase_has_modules_and_schemas():
    assert any((ROOT / 'modules').glob('*.yaml'))
    assert any((ROOT / 'schemas').glob('*.schema.yaml'))
