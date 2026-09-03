from __future__ import annotations
from typing import Iterable, Mapping, Any

def build_phase_health_panel(payloads: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    phases = list(payloads)
    ok = sum(1 for p in phases if p.get('status') == 'PASS')
    fail = sum(1 for p in phases if p.get('status') == 'FAIL')
    warn = sum(1 for p in phases if p.get('status') == 'WARN')
    return {'phase_count': len(phases), 'pass': ok, 'warn': warn, 'fail': fail, 'phases': phases}

def build_global_control_tower(phase_health_panel: Mapping[str, Any], test_summary: Mapping[str, Any]) -> dict[str, Any]:
    decision = 'PASS' if phase_health_panel.get('fail', 0) == 0 and test_summary.get('failed_tests', 0) == 0 else 'FAIL'
    return {'status': decision, 'phase_health': dict(phase_health_panel), 'test_summary': dict(test_summary)}
