# P3 Research Tools Unified RC1 — Merge Report

## Result

The three agent packages were merged into one coherent Phase 3 tree without a last-writer-wins overlay.

- Agent 1 remains the canonical authority for contracts, public IDs, modes, aliases and point-in-time rules.
- Agent 2 contributes corpus, market, options and macro implementations through explicit adapters.
- Agent 3 contributes company, quantitative and runtime/evidence implementations through the same canonical S40 composition layer.
- The original 81 Phase 3 module implementations were preserved.
- The extension adds 47 modules across P3.S32–P3.S40.

Final logical inventory:

| Surface | Count |
|---|---:|
| Preserved legacy P3 modules | 81 |
| Research-tool extension modules | 47 |
| Logical P3 module total | 128 |
| New subphases | 9 |
| Tool families | 6 |
| Public operations | 34 |
| Compatibility aliases | 2 |

## How the merge avoids a Frankenstein architecture

### One contract authority

The Agent 1 catalog is authoritative. Agent 2 and Agent 3 handler names remain private implementation details and are projected to canonical `internal.*` handler IDs.

### One physical namespace

All extension wrappers live under:

```text
src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/modules/
```

No S35–S40 wrapper is duplicated in the legacy `modules/` directory.

### One schema and contract surface

Module contracts and public operation schemas were consolidated under:

```text
contracts/extensions/research_tools/
```

The package contains 34 request schemas and 34 result schemas for the canonical operations. Family-internal schemas are separated from public operation schemas.

### One runtime composition point

S40 now assembles all six families into the existing S21 `ToolGatewayPort`:

```text
research.corpus.v1
market.observation.v1
options.observation.v1
macro.observation.v1
company.fundamentals.v1
quant.diagnostics.v1
```

The registry contains all 34 operations. Corpus, market, options and macro received the missing cross-agent adapters; company and quant were normalized to the same public IDs and envelopes.

### Compatibility without duplicate implementations

```text
research.search_filings.v1
→ research.corpus.v1 / search
```

```text
quant.realized_volatility.v1
→ quant.diagnostics.v1 / realized_volatility
```

Aliases resolve arguments and metadata but never register a second handler.

## Main conflicts resolved

1. **Three wrapper locations** were normalized to the extension namespace.
2. **Three contract/schema layouts** were consolidated under one authority.
3. **Agent 1 aliases and Agent 3 runtime aliases** were connected by an anti-corruption projection.
4. **S40 originally ignored Agent 2 bundles**; it now builds executable operations for corpus, market, options and macro.
5. **Handler IDs diverged**; public IDs now come only from the canonical catalog.
6. **Artifact names diverged**; S40 consumes the canonical operation registry and normalized projections.
7. **No global DAG/registry existed**; unified module, IO, DAG, handler, schema and qualification authorities were generated.
8. **Transient Agent 3 caches** were removed and excluded from release manifests.
9. **Canonical serialization rejected `date` values**; it now handles both aware datetimes and dates deterministically.
10. **Cross-agent evidence contained timestamp strings**; adapters now normalize them to timezone-aware datetimes before canonical result validation.
11. **Legacy multiprocessing used `fork()` in a multithreaded Python 3.13 process**; the hardening test is spawn-first to avoid deadlock risk.

## Canonical authorities

The final package includes:

```text
config/research_tools/MODULE_REGISTRY_S32_S40.yaml
config/research_tools/MODULE_IO_MATRIX_S32_S40.yaml
config/research_tools/RESEARCH_TOOL_EXTENSION_DAG_S32_S40.yaml
config/research_tools/HANDLER_REGISTRY_S32_S40.yaml
config/research_tools/SCHEMA_BINDINGS_S32_S40.yaml
config/research_tools/QUALIFICATION_MATRIX_S32_S40.yaml
config/research_tools/UNIFIED_AUTHORITY_MANIFEST_RC1.yaml
```

The DAG has 47 extension nodes, a single edge format and no cycle. The handler registry covers all 34 public operations.

## Validation

The complete collected suite contains **904 tests**. All **904 passed** in isolated partitions.

| Partition | Passed |
|---|---:|
| Contracts | 248 |
| Final integration | 20 |
| Foundation contracts | 19 |
| Integration runtime | 8 |
| Phase-specific | 227 |
| Research tools | 65 |
| Runtime context | 33 |
| Runtime engine | 2 |
| Runtime hardening | 14 |
| Runtime products | 149 |
| Runtime society | 80 |
| Scientific evaluation | 2 |
| Top-level | 37 |
| **Total** | **904** |

Additional checks:

- Python compilation: PASS.
- Release and file-manifest verification: PASS.
- Cross-agent S40 runtime tests: 7 PASS.
- Registry completeness: 34/34 operations.
- Extension module inventory: 47/47.
- Duplicate extension wrappers in legacy namespace: none.

The isolated matrix is the release evidence because each pytest partition starts with a clean process. This prevents cumulative plugin, thread and multiprocessing state from contaminating later tests. The helper is `tools/run_test_matrix.py`.

## Qualification status

The code is locally integrated and test-qualified, but the release remains fail-closed for production.

The operation-mode qualification matrix contains:

| Status | Records |
|---|---:|
| `IMPLEMENTED_QUALIFIED_LOCAL` | 20 |
| `IMPLEMENTED_LOCAL_DATA_QUALIFICATION_REQUIRED` | 32 |
| `IMPLEMENTED_LOCAL_UPSTREAM_STRUCTURED_DATA_REQUIRED` | 24 |
| `IMPLEMENTED_LOCAL_VINTAGE_QUALIFICATION_REQUIRED` | 12 |
| `IMPLEMENTED_LOCAL_HISTORICAL_SNAPSHOT_QUALIFICATION_REQUIRED` | 9 |

This is intentional:

- company fundamentals still require structured upstream P1/P2 panels for production;
- macro advanced modes require real vintage qualification;
- options advanced modes require real historical chain snapshots;
- market and corpus production use require real-data receipts and consumer evidence;
- MCP, Neo4j and external HTTP are optional and not required by the local backtest path;
- P0 remains the only promotion authority.

## Final decision

The result is a single contract-governed extension, not three packages placed side by side. Public contracts, temporal authority, runtime composition, evidence and downstream projections are unified. Domain-specific code remains isolated by family and can be replaced or improved without changing the public operation surface.
