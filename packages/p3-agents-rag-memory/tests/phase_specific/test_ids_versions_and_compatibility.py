import hashlib
import re
from collections import defaultdict
from .helpers import yaml_load, module_sort_key


def test_subphase_ids_are_contiguous(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    nums=sorted({int(re.search(r'S(\d+)',m['subphase']).group(1)) for m in io['module_io_matrix']})
    assert nums==list(range(1,32))


def test_module_numbers_are_contiguous_inside_each_subphase(plan_root):
    io=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    grouped=defaultdict(list)
    for m in io['module_io_matrix']:
        grouped[m['subphase']].append(int(re.search(r'M(\d+)',m['module_id']).group(1)))
    bad={sid:sorted(nums) for sid,nums in grouped.items() if sorted(nums)!=list(range(1,max(nums)+1))}
    assert not bad


def test_external_schema_hashes_match_frozen_baseline(plan_root):
    baseline=yaml_load(plan_root/'compatibility'/'EXTERNAL_SCHEMA_BASELINE_HASHES.yaml')
    errors=[]
    for row in baseline['schemas']:
        p=plan_root/'schemas'/row['file']
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            errors.append(row['file'])
    assert baseline['schemas']
    assert not errors


def test_required_input_schemas_exist(plan_root):
    c=yaml_load(plan_root/'contracts'/'INPUT_CONTRACTS.yaml')
    models={"FoundationRuntimeManifest","CycleKernelRequest","ReplayState"}
    models |= {p.name.replace(".schema.yaml","") for p in (plan_root/"schemas").glob("*.schema.yaml")}
    missing=[name for name in c['required_boundary_inputs'] if name not in models]
    assert not missing


def test_official_output_schemas_exist(plan_root):
    c=yaml_load(plan_root/'contracts'/'OUTPUT_CONTRACTS.yaml')
    names={p.name.replace('.schema.yaml','') for p in (plan_root/'schemas').glob('*.schema.yaml')}
    missing=[x for x in c['official_outputs'] if x not in names]
    assert not missing


def test_contract_compatibility_version_is_uniform(plan_root):
    inp=yaml_load(plan_root/'contracts'/'INPUT_CONTRACTS.yaml')
    out=yaml_load(plan_root/'contracts'/'OUTPUT_CONTRACTS.yaml')
    ver=yaml_load(plan_root/'contracts'/'VERSION_POLICY.yaml')
    matrix=yaml_load(plan_root/'contracts'/'MODULE_IO_MATRIX.yaml')
    assert inp['contract_compatibility']==out['contract_compatibility']=='V14.1-RC4.1'
    assert ver.get('external_contract_version')=='V14.1-RC4.1'
    assert matrix['rc']=='RC4.1'
