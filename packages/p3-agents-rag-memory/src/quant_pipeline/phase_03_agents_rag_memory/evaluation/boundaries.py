"""Cross-phase output and schema closure checks for production."""
from __future__ import annotations
import hashlib
import yaml
from pathlib import Path

P4_OUTPUTS=("social_feature_panel","evidence_tag_panel","agent_disagreement_panel","context_memory_feature_panel","hypothesis_registry","phase4_social_handoff_manifest")
P9_OUTPUTS=("p9_evaluation_evidence_bundle","p9_context_learning_handoff_manifest")

def _sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_cross_phase_boundaries(root:Path)->dict[str,object]:
    binding=yaml.safe_load((root/'contracts/ARTIFACT_SCHEMA_BINDINGS.yaml').read_text(encoding='utf-8'))
    rows=binding.get('bindings',binding.get('artifact_schema_bindings',[]))
    index={str(row.get('artifact_name') or row.get('artifact')):row for row in rows if isinstance(row,dict)}
    checks={}; hashes={}
    for artifact in P4_OUTPUTS+P9_OUTPUTS:
        schema=root/'schemas'/f'{artifact}.schema.yaml'
        checks[f'{artifact}_schema_exists']=schema.is_file()
        if schema.is_file(): hashes[artifact]=_sha(schema)
        checks[f'{artifact}_binding_exists']=artifact in index
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'schema_hashes':hashes,
        'p4_outputs':P4_OUTPUTS,'p9_outputs':P9_OUTPUTS,'promotion_authority':'P0_P9_EXTERNAL_ONLY'}
