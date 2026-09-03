# P3.S40 Integration Guide

## Installation mode

This package is additive. It installs under the research-tools extension namespace and must not overwrite legacy modules or canonical module tables before the coordinated S32–S40 merge.

## Required upstream artifacts

- S32 operation and mode registries, aliases and extension snapshot;
- S33 point-in-time data boundary;
- S34 entitlement and context projections;
- handler bundles and qualification reports from S35–S39;
- existing S21 raw result, audit, context and snapshot contracts.

## Composition order

1. Place all `ExecutableOperation` objects in `ModuleExecutionContext.services["research_tool_operations"]`.
2. Run M01 and fail when a non-blocked operation is missing a handler.
3. Run M02 and create the process-local gateway through `create_gateway_runtime`.
4. Run M03 against the real S21 provider, policy, entitlement and context models.
5. Inject the gateway into `S21Runtime.tool_gateway`.
6. Execute existing S21.M03.
7. Run S40.M04 and pass `extended_retrieval_evidence_map` to existing S21.M04.
8. Run M05–M08 after validation and belief binding.

## Compatibility status

- S21: executable compatibility proved locally.
- S22: evidence IDs are compatible through the extended retrieval map.
- P4: producer-ready supplemental handoff; consumer not yet wired.
- P9: N+1 evidence is retained locally with `DEFERRED_BY_GOVERNANCE`.
  Global RC4.1 forbids a direct P3→P9 edge, so no cross-phase connection is
  materialized until P0 approves an intermediary or amends the global contract.
- P5: direct connection prohibited.

## Rollback

Remove only files listed by the patch manifest. Existing P3 files are not modified, so rollback does not require restoring legacy bytes.
