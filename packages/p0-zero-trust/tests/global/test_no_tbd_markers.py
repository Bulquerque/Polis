from pathlib import Path

FORBIDDEN = ['TBD_BY_AGENT', 'same_phase_previous_module_or_allowed_phase_input']


def test_no_forbidden_placeholders_in_contracts():
    root = Path(__file__).resolve().parents[2]
    for path in list((root / 'contracts').glob('*.yaml')) + list((root / 'source_of_truth').rglob('*.yaml')):
        text = path.read_text(encoding='utf-8')
        for marker in FORBIDDEN:
            assert marker not in text, f'{marker} found in {path}'
