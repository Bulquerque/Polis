# Phase 1 Integrated Replacement

This package is a compatibility-first integrated replacement for the original Phase 1 ingestion package. It combines the hardened S1/S2 capture architecture with the S3/S4/S5 persistence, integrity, manifest, snapshot and handoff reforms.

## Replacement contract

The external Phase 1 shape is preserved: five subphases, eighteen module IDs, the `run_phase(inputs, config)` entry point, seven phase inputs and seven phase outputs. The package is intended to replace the original `phase_01_ingestion_agent_package_RC4_1` directory.

A minimal P2 compatibility overlay is included separately for `P2.S1.M01_phase1_handoff_validator.py`. It adds fail-closed multi-snapshot matching while retaining legacy unique-source fallback.

## Key improvements

- Canonical `source_id` normalization and capture-level identity (`task_id`, `request_id`, `capture_id`, `raw_artifact_id`, `snapshot_id`).
- `LEGACY_V1` compatibility mode and `CAPTURE_V2` multi-capture mode.
- Provider adapter/credential/HTTP foundation without materializing secrets into artifacts.
- Local-file streaming into atomic storage; exact-byte SHA-256 independent of ingress route.
- Provider attempt/error provenance preserved through S5.
- Soft-failure technical integrity checks instead of losing the error report.
- Multi-snapshot source registry and evidence-based P2 handoff.
- P2 bridge fails closed when snapshots are missing, ambiguous or duplicated.

## Installation

1. Back up the existing Phase 1 package.
2. Replace `phase_01_ingestion/phase_01_ingestion_agent_package_RC4_1` with the directory in this ZIP.
3. Apply the single P2 overlay file at the same relative path shown under `compatibility_overlay/`.
4. Configure credentials externally (`.env`, environment variables or another resolver); do not copy secrets into source definitions.
5. Run the included phase-specific tests, then the repository-wide test harness.

## Important

The ZIP does not include secrets or `.env`. Real provider execution also requires valid source/request definitions and the credentials/entitlements required by those providers. The architecture supports provider-specific extension without changing the frozen public Phase 1 topology.
