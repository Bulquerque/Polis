from __future__ import annotations
import hashlib

def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def test_global_authority_patch_matches_local_and_declared_phase_authorities(root):
    patch=root/'integration/new_version_sanitized/global_authority_patch/schemas'
    for name in ['clean_context_source_panel','clean_document_panel','clean_event_reference_panel','source_quality_panel','context_handoff_manifest','phase3_handoff_manifest','hypothesis_registry']:
      assert (patch/f'{name}.schema.yaml').is_file()
      assert h(patch/f'{name}.schema.yaml')==h(root/'schemas'/f'{name}.schema.yaml')
