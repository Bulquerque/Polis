from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]

def test_documentation_surface_complete():
    required=['README.md','PHASE_OVERVIEW.md','PHASE_FUNCTION.md','SUBPHASES.md','MODULE_CATALOG.md','MODULE_BREAKDOWN.md','DIAGRAM_INTERPRETATION.md','ZERO_TRUST_RULES.md','CODE_STANDARDS.md','TESTING_STANDARDS.md','AGENT_PROMPT.md','REPORT_ALIGNMENT.md']
    for rel in required:
        assert (ROOT/rel).exists(), rel

def test_diagrams_exist():
    d=ROOT/'diagrams'
    for rel in ['phase_00_zero_trust_guardian_diagram.png','phase_00_connection_map.png','phase_00_module_flow.png','phase_00_connection_map.mmd','phase_00_module_flow.mmd']:
        assert (d/rel).exists(), rel

def test_all_modules_have_contracts():
    paths=list((ROOT/'modules').glob('*.yaml'))
    assert len(paths) == 40
    for path in paths:
        data=yaml.safe_load(path.read_text())
        for key in ['module_id','module_name','function','inputs','outputs','validations','fail_fast_conditions','allowed_connections']:
            assert key in data, f'{path.name} missing {key}'

def test_module_io_has_no_generic_connections():
    text=(ROOT/'contracts/MODULE_IO_MATRIX.yaml').read_text()
    assert 'same_phase_previous_module_or_allowed_phase_input' not in text
    assert 'same_phase_next_module_or_declared_phase_output' not in text
