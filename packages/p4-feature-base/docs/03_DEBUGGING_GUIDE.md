# Debugging Guide

## Fastest path to a failure

1. Inspect `result["integration_report"]` to identify which boundary ran.
2. Inspect the relevant subphase `module_results` and reason codes.
3. Validate the input artifact against its schema before debugging mathematics.
4. Trace `lineage_id`, parent feature IDs and `available_at` through the failing record.
5. Reproduce with the smallest domain fixture, then run the integrated fixture.

## Common failure classes

### S1 hash or manifest mismatch

The artifact was changed after its handoff manifest was created. Rebuild the manifest; never disable hash validation.

### S2 future availability

Check both run-level and record-level decision times. Historical records should carry an explicit per-record `decision_time`; snapshot records intentionally inherit the run cutoff.

### S4 duplicate observation

The canonical key is `(decision_time, entity_id, variable_id)`. Duplicates usually indicate unresolved revisions, duplicate sources or an incorrect backfill decision-time policy.

### S6→S7 schema issue

Use only `horizon_panel_for_s7`. Do not rename fields manually. Confirm that composite availability is derived from all parents.

### S8 non-finite state

All-missing or zero-variance columns are excluded from a fold and recorded as degraded. NaN/Inf must never enter a content hash or fit-state manifest.

### S9 handoff blocked

Inspect `p4_quality_gate_decision` before changing code. A sparse upstream family can correctly block or degrade the handoff while the pipeline itself remains successfully executed.

## Test layers

- Unit/domain tests: tiny mathematical oracles and metamorphic properties.
- Subphase tests: one subphase with deterministic artifacts.
- Boundary tests: S3→S4 and S6→S7 adapters.
- Integrated test: raw P2/P3 fixtures through S1→S9.
- Live qualification: external and not included in unit CI.

The old S5/S6 suites repeatedly rebuild large upstream fixtures. They remain useful as qualification evidence but should not be the default debugging loop. The integrated package provides a session-scoped end-to-end fixture instead.
