from __future__ import annotations
from typing import Mapping, Any

def decide_release_gate(global_test_report: Mapping[str, Any], forbidden_connection_report: Mapping[str, Any], code_quality_report: Mapping[str, Any], hash_integrity_report: Mapping[str, Any]) -> dict[str, Any]:
    blocking = []
    if global_test_report.get('failed_tests', 0): blocking.append('failed_tests')
    if forbidden_connection_report.get('forbidden_connections', 0): blocking.append('forbidden_connections')
    if code_quality_report.get('critical_findings', 0): blocking.append('critical_code_quality')
    if hash_integrity_report.get('missing_hashes', 0): blocking.append('missing_hashes')
    return {'decision': 'FAIL' if blocking else 'PASS', 'blocking_reasons': blocking}
