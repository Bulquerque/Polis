
from .helpers import yaml_load

REQUIRED_FIELDS={'module_id','module_name','phase','subphase','status','function','inputs','outputs','validations','invariants','non_responsibilities','fail_fast_conditions','forbidden_fields','allowed_connections','tests_required','definition_of_done','observability_requirements','debugging_contract','change_control','review_checklist'}

def _modules(plan_root):
    return [yaml_load(p) for p in sorted((plan_root/'modules').glob('*.yaml'))]

def test_module_ids_are_unique(plan_root):
    ids=[m['module_id'] for m in _modules(plan_root)]
    assert len(ids)==len(set(ids))

def test_module_specs_have_required_fields(plan_root):
    missing={m['module_id']:sorted(REQUIRED_FIELDS-set(m)) for m in _modules(plan_root) if REQUIRED_FIELDS-set(m)}
    assert not missing

def test_module_specs_match_io_matrix(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    im={m['module_id']:m for m in io['module_io_matrix']}
    sm={m['module_id']:m for m in _modules(plan_root)}
    assert set(im)==set(sm)
    mismatches=[]
    for mid in im:
        if im[mid]['consumes_from']['artifacts']!=sm[mid]['inputs'] or im[mid]['emits_to']['artifacts']!=sm[mid]['outputs'] or im[mid]['subphase']!=sm[mid]['subphase']:
            mismatches.append(mid)
    assert not mismatches

def test_all_modules_reject_phase_forbidden_fields(plan_root):
    forbidden=set(yaml_load(plan_root/'contracts'/'FORBIDDEN_FIELDS.yaml')['forbidden_fields'])
    missing=[m['module_id'] for m in _modules(plan_root) if not forbidden <= set(m['forbidden_fields'])]
    assert not missing

def test_every_module_has_meaningful_tests(plan_root):
    empty=[m['module_id'] for m in _modules(plan_root) if len(m.get('tests_required',[]))<1]
    assert not empty
