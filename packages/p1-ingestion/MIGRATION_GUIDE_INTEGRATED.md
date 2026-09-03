# Migration Guide — Original P1 to Integrated Replacement

## Minimal-change path

- Keep existing callers and phase input/output names unchanged.
- Start with `LEGACY_V1` (default) for maximum compatibility.
- Apply the included P2.S1.M01 overlay before enabling `CAPTURE_V2`.
- Move to `CAPTURE_V2` only when source definitions intentionally use multiple datasets/partitions/pages per source.

## Rollback

Rollback is directory-level: restore the backed-up original P1 directory and original P2.S1.M01 file. No database migration is required by this package.

## Credential handling

`credential_handle` values are references only. Actual credentials must be resolved at runtime. Query-string URLs are sanitized before persistence, including common API-key/token/secret parameter names.

## Compatibility guarantee scope

The package preserves the public Phase 1 topology and has regression tests for the original phase behavior plus new hardening tests. Absolute absence of bugs cannot be guaranteed for every future provider response or environment; the included validation report records the exact tests run for this artifact.
