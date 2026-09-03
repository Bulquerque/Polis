
import re
from .helpers import yaml_load

def test_every_subphase_has_prompt_and_test_spec(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    sids=sorted({m['subphase'] for m in io['module_io_matrix']})
    prompts={re.search(r'(P3_S\d+)',p.name).group(1).replace('_','.') for p in (plan_root/'subphases').glob('*.md')}
    specs={p.stem.replace('_TEST_SPEC','').replace('_','.') for p in (plan_root/'tests'/'specifications'/'subphases').glob('*.yaml')}
    assert set(sids)==prompts==specs

def test_subphase_prompts_have_required_sections(plan_root):
    required=['## 1. Missão','## 3. Dependências','## 4. Módulos','## 6. Inputs','## 7. Outputs','## 10. Falhas','## 12. Testes','## 13. Definition of Done']
    bad={}
    for p in (plan_root/'subphases').glob('*.md'):
        text=p.read_text(encoding='utf-8')
        miss=[x for x in required if x not in text]
        if miss: bad[p.name]=miss
    assert not bad

def test_subphase_test_specs_cover_all_modules(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    expected={}
    for m in io['module_io_matrix']: expected.setdefault(m['subphase'],set()).add(m['module_id'])
    errors={}
    for p in (plan_root/'tests'/'specifications'/'subphases').glob('*.yaml'):
        d=yaml_load(p); actual={m['module_id'] for m in d['modules']}
        if actual!=expected[d['subphase']]: errors[d['subphase']]=(expected[d['subphase']],actual)
    assert not errors

def test_supertest_catalog_is_complete(plan_root):
    specs=list((plan_root/'tests'/'specifications'/'supertests').glob('ST*.yaml'))
    assert len(specs)>=20
    for p in specs:
        d=yaml_load(p)
        assert d['objective'] and d['required_cases'] and d['required_evidence']
