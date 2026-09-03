# P3.S32 — Local Qualification Report

## Scope

This report qualifies **P3.S32 — Research Tool Contract & Compatibility Foundation** as an internal, offline, contract-level extension of the existing Phase 3 package.

It does **not** qualify external providers, live MCP sessions, downstream handlers from S35–S40, or production promotion. Those remain explicitly out of scope and fail closed.

## Implemented modules

- `P3.S32.M01 canonical_research_tool_catalog_builder`
- `P3.S32.M02 research_mode_contract_registry_builder`
- `P3.S32.M03 legacy_tool_plane_compatibility_overlay_builder`
- `P3.S32.M04 extension_snapshot_manifest_builder`

The wrappers, contracts, schemas and subphase documentation are isolated under extension namespaces so the frozen `P3.S1–P3.S31` registries remain unchanged.

## Contract surface

- 6 canonical tool families
- 34 public operations
- 2 legacy aliases
- 86 generated JSON Schemas
- JSON Schema dialect: Draft 2020-12
- strict Pydantic v2 models with forbidden extra fields
- deterministic hashing and order-independent configuration canonicalization
- external MCP/HTTP providers represented as optional transports, never pre-qualified by static configuration

## Test evidence

The following independent groups were executed with bounded timeouts, bytecode disabled and pytest cache disabled where possible:

- 23 focused S32 tests
- 267 contract and foundation tests
- 33 runtime-context tests
- 80 runtime-society tests
- 149 runtime-product tests
- 2 runtime-engine tests
- 14 runtime-hardening tests
- 2 scientific-evaluation tests
- 27 final/runtime integration tests excluding the release test until final manifest regeneration
- 1 final release integrity test after manifest regeneration
- 142 legacy phase-specific tests across bounded batches
- 36 root compatibility and adapter tests
- 81 legacy module metadata/contract checks in bounded import batches
- 86 JSON Schemas validated against the Draft 2020-12 metaschema
- 8 YAML configurations validated through their Pydantic models

No functional test failed after the compatibility isolation fixes. Intermediate timeouts were caused by aggregate import/test processes; affected files were rerun in smaller bounded groups and passed.

## Compatibility corrections made during qualification

1. S32 wrappers moved from the frozen legacy module namespace to `extensions/research_tools/modules/`.
2. S32 contracts moved from the frozen legacy contract directory to `contracts/extensions/research_tools/modules/`.
3. S32 schemas moved from the frozen global schema registry to `contracts/extensions/research_tools/schemas/`.
4. S32 subphase documentation moved to `subphases/extensions/research_tools/`.
5. Generic `common.py` was replaced by the semantic name `artifact_construction.py`.
6. Broad exception capture in mode validation was narrowed to `pydantic.ValidationError`.
7. Configuration canonicalization was made order-invariant.
8. Catalog validation now enforces all forbidden authorities and frozen family/operation counts.

## API and standards review

The design was checked against:

- Model Context Protocol specification and official Python SDK documentation: tools have explicit identifiers and schemas, while transport remains a separate concern.
- JSON Schema Draft 2020-12: all generated schemas declare and validate against this dialect.
- Pydantic v2 configuration: strict validation, frozen models and forbidden extra fields are used for contract authority.

No MCP SDK dependency is required for this subphase because S32 defines contracts and compatibility projections only. MCP remains an optional future transport.

## Qualification result

```text
IMPLEMENTED_QUALIFIED_INTERNAL
production_promotion_allowed = false
external_provider_qualification = not_performed
P0_independent_qualification = pending
```

## Reproduction

```bash
PYTHONPATH=src python -m pytest -q tests/phase_specific/research_tools
PYTHONPATH=src python tools/research_tools/build_s32_manifests.py
PYTHONPATH=src python tools/research_tools/generate_s32_contracts.py
PYTHONPATH=src python tools/release.py verify
```
