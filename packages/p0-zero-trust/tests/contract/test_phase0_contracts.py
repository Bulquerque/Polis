from pathlib import Path
import yaml, json
ROOT = Path(__file__).resolve().parents[2]

def y(p): return yaml.safe_load((ROOT/p).read_text(encoding='utf-8')) or {}

def test_phase0_contracts_exist():
    for rel in ['contracts/INPUT_CONTRACTS.yaml','contracts/OUTPUT_CONTRACTS.yaml','contracts/MODULE_IO_MATRIX.yaml','contracts/CONNECTIONS.yaml']:
        assert (ROOT/rel).exists(), rel

def test_phase0_outputs_have_schema_and_producer():
    out = y('contracts/OUTPUT_CONTRACTS.yaml')['outputs']
    rows = y('contracts/MODULE_IO_MATRIX.yaml')['module_io_matrix']
    produced = {a for r in rows for a in r['emits_to']['artifacts']}
    for artifact in out:
        assert artifact in produced, artifact
        assert (ROOT/'schemas'/f'{artifact}.schema.yaml').exists(), artifact

def test_phase0_does_not_allow_economic_fields():
    forbidden = set(y('contracts/FORBIDDEN_FIELDS.yaml')['forbidden_fields'])
    assert 'trade_decision' in forbidden
    assert 'realized_pnl' in forbidden
    assert 'rank_score' in forbidden

def test_phase0_fixtures_exist():
    for rel in ['fixtures/input/minimal_input_fixture.json','fixtures/output/minimal_output_fixture.json']:
        data = json.loads((ROOT/rel).read_text(encoding='utf-8'))
        assert data['pipeline_version'] == 'V14.1-RC4.1'
