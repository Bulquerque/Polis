# P1 Integrated Replacement — Compatibility Matrix

> Goal: replace the original Phase 1 package with minimal external change while preserving all public phase topology and strengthening internal behavior.

## Frozen public surface

- 5 subphases preserved.
- 18 module IDs preserved.
- `run_phase(inputs, config)` preserved.
- 7 phase input names preserved.
- 7 phase output names preserved.
- P1 remains raw-ingestion/custody only; economic cleaning remains outside P1.

## Module-by-module comparison

| Module | Name | Original | Integrated replacement | Compatibility |
|---|---|---|---|---|
| P1.S1.M01 | source_registry_loader | Simple source merge and shallow identity assumptions | Canonicalized source IDs; recursive secret/forbidden validation; adapter aliases; dataset/provider metadata | PRESERVED + STRENGTHENED |
| P1.S1.M02 | ingestion_run_config_validator | Minimal run_id/calendar validation | RunContext semantics, UTC normalization, contract modes, policies, optional credential-handle allowlist | PRESERVED + STRENGTHENED |
| P1.S1.M03 | source_availability_planner | Approximately one task per source; weak temporal semantics | Multi-dataset/partition planning, explicit CAPTURE_V2, early legacy-pagination block, no fabricated availability | SUPERSET WITH LEGACY MODE |
| P1.S2.M01 | source_capture_orchestrator | Task manifest pass-through | Stable lifecycle-ready task manifest with provider/adapter/dataset grain | PRESERVED + STRENGTHENED |
| P1.S2.M02 | b3_cotahist_raw_fetcher | Local/raw materializer | Compatibility wrapper over provider-aware capture runtime; exact raw semantics | PRESERVED + EXTENSIBLE |
| P1.S2.M03 | macro_raw_fetcher | Local/raw materializer | Adapter-dispatched macro capture with credentials/HTTP/pagination support | PRESERVED + EXTENSIBLE |
| P1.S2.M04 | benchmark_raw_fetcher | Local/raw materializer | Adapter-dispatched market/benchmark capture with provider metadata | PRESERVED + EXTENSIBLE |
| P1.S2.M05 | crypto_raw_fetcher | Local/raw materializer | Adapter-dispatched crypto capture preserving venue/provider identity | PRESERVED + EXTENSIBLE |
| P1.S2.M06 | document_raw_collector | Raw text/file collector | Provider-aware document capture while retaining manual-text compatibility | PRESERVED + EXTENSIBLE |
| P1.S2.M07 | non_b3_capture_inventory_assembler | source_id-oriented aggregation | capture_id-oriented aggregation; same source may produce many captures; attempts retained | STRENGTHENED |
| P1.S3.M01 | raw_artifact_writer | Simple filesystem write/no-overwrite | Atomic chunked write, file-backed streaming, multi-capture identity, concurrent exclusive publish check | STRENGTHENED |
| P1.S3.M02 | hash_version_manager | Basic hash and size | Exact-byte SHA-256, post-write verification, version_id, attempt propagation | STRENGTHENED |
| P1.S4.M01 | raw_readability_checker | Basic empty/JSON/HTML checks | Soft-failure technical integrity checks for JSON/XML/ZIP/GZIP/Parquet plus archive safety limits | STRENGTHENED |
| P1.S4.M02 | raw_schema_hint_detector | Mostly extension/format hint | Structural fingerprint with keys/columns/container hints; unreadable becomes not_applicable | STRENGTHENED |
| P1.S5.M01 | ingestion_manifest_builder | Effectively required all tasks completed | Task lifecycle reconciliation, partial success, real provider attempt cause preservation | STRENGTHENED |
| P1.S5.M02 | source_snapshot_registry_builder | One snapshot per source assumptions | snapshot_id grain; multiple captures/snapshots per source; separate reference/availability time | STRENGTHENED |
| P1.S5.M03 | ingestion_error_report_builder | Mostly NO_ERROR placeholders | Canonical error report derived from provider/integrity/readability evidence | REPLACED WITH COMPATIBLE OUTPUT |
| P1.S5.M04 | phase2_handoff_packager | Defaults and source-level assumptions | Evidence joins by snapshot/artifact/capture; no fabricated reference time; multi-snapshot handoff | STRENGTHENED |

## Compatibility modes

### LEGACY_V1
Default compatibility mode. Preserves single-capture-per-source constraints where required for old callers and rejects incompatible pagination/multi-capture before network execution.

### CAPTURE_V2
Modern mode. Supports one source producing multiple datasets, partitions, pages, captures, raw artifacts and snapshots. Requires the included P2.S1.M01 compatibility bridge for strict multi-snapshot handoff validation.

## Intentional non-goals

- No economic cleaning, canonical ticker mapping, corporate-action adjustment, feature engineering or forecasting in P1.
- No `.env` or credential material is included in the ZIP.
- Provider adapters provide the transport/authentication architecture; provider-specific catalog/discovery coverage can be extended without changing the 18-module topology.
