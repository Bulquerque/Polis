from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_cross_phase_matrix_covers_p0_through_p8_once():
    data=json.loads((ROOT/'registries/cross_phase_compatibility_matrix.json').read_text())
    ids=[row['phase_id'] for row in data['entries']]
    assert ids == [f'P{i}' for i in range(9)]
    assert len(ids)==len(set(ids))
    assert all(len(row['fingerprint_sha256'])==64 for row in data['entries'])
    assert data['p9_version']=='0.1.0rc4.post2'

def test_cross_phase_invariants_keep_authority_and_no_fabrication():
    data=json.loads((ROOT/'registries/cross_phase_compatibility_matrix.json').read_text())
    text=' '.join(data['invariants']).lower()
    assert 'p0 remains the only activation authority' in text
    assert 'never synthesized' in text
    assert next(x for x in data['entries'] if x['phase_id']=='P3')['state']=='COMPATIBLE_PROCESS_ISOLATED'
