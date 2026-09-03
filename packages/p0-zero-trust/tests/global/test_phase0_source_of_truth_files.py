from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase0_source_of_truth_files_exist():
    required = [
        'source_of_truth/standards/CODE_STANDARDS.md',
        'source_of_truth/standards/TESTING_STANDARDS.md',
        'source_of_truth/standards/ZERO_TRUST_RULES.md',
        'source_of_truth/standards/MINIMAL_CODE_POLICY.md',
        'source_of_truth/standards/SEARCH_FIRST_PATCH_ONLY_POLICY.md',
        'source_of_truth/standards/ARTIFACT_STYLE_GUIDE.md',
        'source_of_truth/registries/phase_registry.yaml',
        'source_of_truth/registries/test_ownership_registry.yaml',
        'source_of_truth/registries/external_data_source_registry.yaml',
        'source_of_truth/registries/llm_model_registry.yaml',
        'source_of_truth/registries/state_sync_canonical_outputs.yaml',
    ]
    missing = [item for item in required if not (ROOT / item).exists()]
    assert not missing, missing
