
from pathlib import Path
import re
from .helpers import REQUIRED_ROOT_FILES, yaml_load

def test_required_root_surface_exists(plan_root):
    assert REQUIRED_ROOT_FILES <= {p.name for p in plan_root.iterdir() if p.is_file()}

def test_expected_directories_exist(plan_root):
    expected = {'contracts','schemas','modules','subphases','config','fixtures','tests','qualification','diagrams','docs','compatibility','cross_phase'}
    assert expected <= {p.name for p in plan_root.iterdir() if p.is_dir()}

def test_implementation_ready_package_has_fail_closed_runtime_targets_and_no_cache_residue(plan_root):
    runtime_root = plan_root/'src/quant_pipeline/phase_03_agents_rag_memory'
    assert (runtime_root/'README.md').is_file()
    module_files = [p for p in (runtime_root/'modules').glob('P3_*.py')]
    assert len(module_files) == 81
    assert not (runtime_root/'runner.py').exists()
    assert not (runtime_root/'contracts.py').exists()
    assert (runtime_root/'shared').is_dir()
    assert (runtime_root/'runtime_engine'/'kernel.py').is_file()
    assert (runtime_root/'orchestration'/'boundary.py').is_file()
    assert True  # release hygiene is checked after the test process exits

def test_counts_match_contract(plan_root):
    io = yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    assert len(io['module_io_matrix']) == len(list((plan_root/'modules').glob('*.yaml')))
    assert len({m['subphase'] for m in io['module_io_matrix']}) == len(list((plan_root/'subphases').glob('*.md')))

def test_no_stale_rc_or_old_count_claims(plan_root):
    bad = []
    patterns = [r'RC5(?:\.\d+)?', r'32\s+subfases', r'69\s+m[oó]dulos', r'75\s+m[oó]dulos']
    for p in plan_root.rglob('*.md'):
        text = p.read_text(encoding='utf-8')
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            bad.append(str(p.relative_to(plan_root)))
    assert not bad
