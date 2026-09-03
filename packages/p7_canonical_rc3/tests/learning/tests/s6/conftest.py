from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json, yaml, pytest
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest

ROOT=Path(__file__).resolve().parents[2]
@pytest.fixture
def bundle(): return json.loads((ROOT/'fixtures/integration/s6_input_bundle.json').read_text())
@pytest.fixture
def config(): return yaml.safe_load((ROOT/'configs/s6_default_config.yaml').read_text())

def rehash(artifact):
    artifact['record_count']=len(artifact['records']); artifact['content_sha256']=digest(artifact['records'])
    artifact['artifact_id']=f"{artifact['artifact_name']}-{artifact['content_sha256'][:16]}"; return artifact

def rebuild_tournament_manifest(bundle):
    names=['comparison_group_registry','pareto_candidate_panel','factor_adjusted_candidate_panel','interpretable_score_panel','interpretable_score_decomposition_panel','metric_semantics_registry','candidate_lineage_panel','tournament_audit_report']
    refs=[{'artifact_name':n,'artifact_id':bundle[n]['artifact_id'],'content_sha256':bundle[n]['content_sha256'],'record_count':bundle[n]['record_count'],'schema_version':bundle[n]['schema_version']} for n in sorted(names)]
    record=bundle['interpretable_tournament_handoff_manifest']['records'][0]
    record['artifact_references']=refs;record['reference_count']=len(refs);record['content_sha256']=digest(refs)
    rehash(bundle['interpretable_tournament_handoff_manifest'])

def clone(value): return deepcopy(value)
