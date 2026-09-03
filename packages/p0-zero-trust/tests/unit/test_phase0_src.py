from pathlib import Path
import sys, tempfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from quant_pipeline.phase_00_zero_trust_guardian.validators import scan_forbidden_fields, validate_no_forbidden_fields, ZeroTrustValidationError
from quant_pipeline.phase_00_zero_trust_guardian.hashing import sha256_file, build_hash_manifest
from quant_pipeline.phase_00_zero_trust_guardian.dashboards import build_phase_health_panel
from quant_pipeline.phase_00_zero_trust_guardian.release import decide_release_gate

def test_forbidden_field_scanner():
    assert scan_forbidden_fields(['date','rank_score']) == {'rank_score'}

def test_validate_no_forbidden_fields_raises():
    try:
        validate_no_forbidden_fields(['trade_decision'], 'ctx')
    except ZeroTrustValidationError:
        return
    assert False

def test_hash_manifest():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'a.txt'; p.write_text('x')
        assert sha256_file(p)
        rows=build_hash_manifest(d)
        assert rows and rows[0]['path']=='a.txt'

def test_dashboard_and_release():
    panel=build_phase_health_panel([{'status':'PASS'},{'status':'WARN'}])
    assert panel['phase_count']==2
    report=decide_release_gate({'failed_tests':0},{'forbidden_connections':0},{'critical_findings':0},{'missing_hashes':0})
    assert report['decision']=='PASS'
