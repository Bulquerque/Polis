import json
from pathlib import Path
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import ReasonCode
ROOT=Path(__file__).parents[1]
def test_module_registry():
    data=json.loads((ROOT/'registries/s10/modules.json').read_text())
    assert [x['module_id'] for x in data]==['P8.S10.M01','P8.S10.M02','P8.S10.M03','P8.S10.M04']
def test_reason_registry_matches_enum():
    data=json.loads((ROOT/'registries/s10/reason_codes.json').read_text())
    assert set(data)=={item.value for item in ReasonCode}
def test_contracts_forbid_promotion():
    text=(ROOT/'subphases/s10/contracts/AUTHORITY_BOUNDARIES.md').read_text(encoding='utf-8')
    assert 'não promove' in text.lower(); assert 'P9' in text and 'P0' in text
