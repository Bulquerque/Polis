from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
EXPECTED_SCHEMA_VERSION = 'v14.1-rc4.1'


def test_all_schema_files_use_the_current_release_version():
    schema_files = sorted(ROOT.rglob('*.schema.yaml'))
    assert schema_files, 'no schema files found'

    mismatched = []
    for path in schema_files:
        if any(part in {"assets", "docs", "src"} for part in path.parts):
            continue
        if "phase_04_extracted" in path.parts:
            # P4 V14.9 is an explicit downstream compatibility release.
            continue
        if "P5_P9_P0_P4_COMPAT_RC3_HARDENED_6" in path.parts:
            # Retained RC3 compatibility components are outside the current
            # RC4.1 schema authority.
            continue
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        if data.get('schema_id') == 'mcp_gateway_policy.v2':
            # This P3 artifact has an independent, contract-bound schema
            # version (2.0.0); its release membership is verified by the P3
            # schema-binding tests and must not be rewritten to the workspace
            # release label.
            continue
        version = data.get('schema_version')
        if version != EXPECTED_SCHEMA_VERSION:
            mismatched.append((path, version))

    assert not mismatched, mismatched
