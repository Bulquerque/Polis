
import json
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from .helpers import all_yaml, all_json

def test_all_yaml_parse(plan_root):
    errors=[]
    for p in all_yaml(plan_root):
        try: yaml.safe_load(p.read_text(encoding='utf-8'))
        except Exception as exc: errors.append((str(p),str(exc)))
    assert not errors

def test_all_json_parse(plan_root):
    errors=[]
    for p in all_json(plan_root):
        try: json.loads(p.read_text(encoding='utf-8'))
        except Exception as exc: errors.append((str(p),str(exc)))
    assert not errors

def test_internal_json_schemas_are_valid(plan_root):
    errors=[]
    for p in (plan_root/'schemas').rglob('*.schema.yaml'):
        schema=yaml.safe_load(p.read_text(encoding='utf-8'))
        try: Draft202012Validator.check_schema(schema)
        except Exception as exc: errors.append((str(p),str(exc)))
    for p in (plan_root/'cross_phase'/'schemas').glob('*.schema.yaml'):
        schema=yaml.safe_load(p.read_text(encoding='utf-8'))
        try: Draft202012Validator.check_schema(schema)
        except Exception as exc: errors.append((str(p),str(exc)))
    assert not errors

def test_valid_internal_examples_match_named_schemas(plan_root):
    mapping={
      'person_profile.example.json':'person_profile.schema.yaml',
      'belief_state.example.json':'belief_state.schema.yaml',
      'stimulus.example.json':'stimulus.schema.yaml',
      'endogenous_stimulus_queue.example.json':'endogenous_stimulus_queue.schema.yaml',
      'cycle_state_snapshot.example.json':'cycle_state_snapshot.schema.yaml',
      'research_budget_ledger.example.json':'research_budget_ledger.schema.yaml',
      'belief_outcome_commitment_log.example.json':'belief_outcome_commitment_log.schema.yaml',
      'textual_gradient_report.example.json':'textual_gradient_report.schema.yaml',
      'synthetic_society_state.example.json':'synthetic_society_state.schema.yaml',
    }
    errors=[]
    for example,schema_name in mapping.items():
        data=json.loads((plan_root/'fixtures'/'internal_examples'/example).read_text(encoding='utf-8'))
        schema=yaml.safe_load((plan_root/'schema_components'/'internal_planned'/schema_name.replace('.schema.yaml','.yaml')).read_text(encoding='utf-8'))
        try:
            schema_path = plan_root/'schema_components'/'internal_planned'/schema_name.replace('.schema.yaml','.yaml')
            registry = Registry()
            for ref_path in (plan_root/'schema_components'/'internal_planned').glob('*.yaml'):
                ref_schema = yaml.safe_load(ref_path.read_text(encoding='utf-8'))
                ref_schema = dict(ref_schema)
                ref_schema.setdefault('$id', ref_path.resolve().as_uri())
                registry = registry.with_resource(ref_path.resolve().as_uri(), Resource.from_contents(ref_schema, default_specification=DRAFT202012))
            schema = dict(schema)
            schema.setdefault('$id', schema_path.resolve().as_uri())
            Draft202012Validator(schema, registry=registry).validate(data)
        except Exception as exc: errors.append((example,str(exc)))
    assert not errors
