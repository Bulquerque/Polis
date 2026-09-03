# P1.S3–P1.S5 Final Compatibility Implementation Report

Scope: compatibility-first modernization of Phase 1 persistence/integrity/closure (P1.S3–P1.S5), plus the smallest upstream/downstream compatibility repairs required to make those semantics actually work end-to-end.

## Frozen architecture preserved

The following public surfaces remain unchanged:

- five P1 subphases;
- all 18 P1 module IDs;
- all existing module entrypoints `run_module(inputs, config)`;
- `run_phase(inputs, config)` public entrypoint;
- the seven public P1 outputs consumed by P2;
- `MODULE_IO_MATRIX.yaml`, input/output contracts, module catalog and phase topology.

No economic cleaning, target construction, feature engineering, signal generation, portfolio logic or backtest logic was moved into P1.

## Compatibility repairs added outside S3–S5

Three small P1.S1 compatibility fixes were necessary because the previous S5 code had been hiding upstream defects with fabricated defaults:

- `P1.S1.M01`: preserves a canonical `source_name` (with an explicit inferred flag when it falls back to `source_id`) and recursively rejects materialized secrets/forbidden economic fields.
- `P1.S1.M02`: recursively rejects materialized credentials and keeps the actual run context.
- `P1.S1.M03`: propagates the real `run_id`, source metadata and explicit reference-time metadata into capture tasks.

The shared P1 raw helper was also corrected so exact raw SHA-256 is identical whether bytes arrive inline or through a file, and capture aggregation is keyed by `capture_id` rather than assuming `source_id` is unique.

## P1.S3 — persistence, hashing and version metadata

### P1.S3.M01 raw_artifact_writer

- supports multiple captures from the same `source_id` using deterministic `capture_id` / `raw_artifact_id` identities;
- preserves the existing flat artifact-root compatibility path while making filenames capture-unique;
- performs atomic local writes using temporary file + `fsync` + `os.replace`;
- streams file-backed artifacts in chunks instead of calling `Path.read_bytes()`;
- preserves no-overwrite semantics;
- keeps a backwards-compatible inline path for unit/local execution without configured storage;
- carries request/capture/temporal metadata without economic normalization.

### P1.S3.M02 hash_version_manager

- SHA-256 is computed from exact raw bytes;
- hashing is route-independent (inline bytes and a file containing identical bytes yield the same digest);
- file-backed hashing is chunked;
- verifies the hash observed during write against the post-write artifact;
- validates optional frozen expected SHA-256;
- emits deterministic version identity metadata.

## P1.S4 — technical integrity and structural hints

### P1.S4.M01 raw_readability_checker

- fail-soft technical classification instead of terminating the evidence chain;
- detects empty/missing artifacts, content-length mismatch, malformed JSON/XML, HTML masquerading as CSV, ZIP/GZIP corruption and basic Parquet-container corruption;
- file-backed checks use paths/streams where practical rather than materializing raw byte copies;
- emits explicit issue codes and technical diagnostics only.

### P1.S4.M02 raw_schema_hint_detector

- unreadable raw artifacts return `not_applicable` instead of raising;
- emits structural fingerprints (JSON keys, CSV columns/delimiter/encoding, ZIP member summaries) without economic cleaning;
- keeps `is_clean_schema = false`;
- uses file-backed inspection where practical.

## P1.S5 — reconciliation, snapshots, errors and handoff

### P1.S5.M01 ingestion_manifest_builder

- every planned task receives an explicit final state;
- supports success, partial and failure outcomes instead of requiring every attempted task to have a completed file;
- reconciles by task/capture/artifact identity rather than collapsing everything to `source_id`.

### P1.S5.M02 source_snapshot_registry_builder

- snapshot uniqueness is based on `snapshot_id`, not `source_id`;
- supports multiple snapshots/captures from one provider;
- propagates the real run identity;
- removes `run-fixture` and hardcoded `readable` defaults;
- keeps reference time and availability time semantically separate and records reference-time provenance.

### P1.S5.M03 ingestion_error_report_builder

- derives explicit errors from real task/readability outcomes;
- distinguishes blocking/non-blocking and retryable outcomes;
- retains legacy `NO_ERROR` records only for actual successful task states;
- preserves the error report even when a task fails.

### P1.S5.M04 phase2_handoff_packager

- preserves all seven public P1 outputs;
- builds handoff records from deterministic joins instead of fabricated values;
- propagates the actual `run_id`;
- never derives `source_reference_date` from `available_at`;
- supports unique handoff records per snapshot/capture;
- blocks only on actual blocking conditions.

## P2 compatibility bridge

`P2.S1.M01 phase1_handoff_validator` was minimally upgraded without changing its public inputs/outputs:

1. match by `snapshot_id` when available;
2. otherwise match by `raw_artifact_id`;
3. only then allow the old `source_id` fallback when exactly one snapshot exists for that source;
4. fail closed on ambiguous legacy multi-snapshot mappings.

This preserves legacy single-snapshot bundles while supporting the new multi-capture P1 semantics.

## Verification results

- Original P1 phase-specific tests: **56 passed**.
- Final P1 phase-specific tests: **65 passed**.
- Original P2 phase-specific tests: **44 passed**.
- Final P2 phase-specific tests: **46 passed**.
- Targeted cross-package/global regression set (excluding three failures reproduced unchanged in the original repository): **193 passed**.
- Python compilation of modified P1/P2 sources: **PASS**.
- P1 package-local manifest: **internally consistent**.
- P2 package-local manifest: **internally consistent**.

A repository-wide manifest audit still reports the same pre-existing Phase 0 mismatch present in the supplied original ZIP; it is outside this patch and was deliberately not rewritten.

## Original-vs-final adversarial comparison

Using identical inputs in separate Python processes:

| Scenario | Original | Final |
|---|---|---|
| actual `run_id` and distinct reference/availability time | FAIL (`run-fixture`, reference=availability) | PASS |
| two captures from same `source_id` | FAIL (`source_id must be unique`) | PASS |
| exact SHA-256 for inline bytes | FAIL (wrong digest semantics) | PASS |
| S3→hash chain without `artifact_root` | FAIL | PASS |
| malformed JSON reaches schema-hint stage fail-soft | FAIL (pipeline abort) | PASS |
| nested API secret inside source definition | ACCEPTED | REJECTED |
| P2 validates two snapshots from same source | FAIL | PASS (2/2 matched) |

Result in this comparison matrix: **original 0/7; final 7/7**.

## Remaining boundaries

This report proves superiority of the final version over the supplied original on the scoped persistence, integrity, closure, security and P1→P2 compatibility scenarios above. It does **not** claim that Phase 1 as a whole is production-complete: real provider adapters, provider-aware discovery/planning, rate/quota handling and full live/bulk network ingestion remain separate workstreams.

The legacy availability planner still contains a compatibility fallback timestamp when no provider/source availability is supplied; the new task marks this condition as inferred rather than silently treating it as authoritative. A later provider-aware S1 modernization should remove that fallback from production qualification paths.
