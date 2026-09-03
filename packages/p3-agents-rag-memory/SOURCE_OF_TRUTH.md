# Source of Truth Binding — P3

This package follows the single RC4.1 authority:

```text
global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/source_of_truth/
```

## Canonical standards

- `CODE_STANDARDS.md` → `source_of_truth/standards/CODE_STANDARDS.md`
- `TESTING_STANDARDS.md` → `source_of_truth/standards/TESTING_STANDARDS.md`
- `ZERO_TRUST_RULES.md` → `source_of_truth/standards/ZERO_TRUST_RULES.md`
- `ARTIFACT_STYLE_GUIDE.md` → `source_of_truth/standards/ARTIFACT_STYLE_GUIDE.md`
- `MINIMAL_CODE_POLICY.md` → `source_of_truth/standards/MINIMAL_CODE_POLICY.md`
- `SEARCH_FIRST_PATCH_ONLY_POLICY.md` → `source_of_truth/standards/SEARCH_FIRST_PATCH_ONLY_POLICY.md`
- `POINT_IN_TIME_AI_POLICY.md` → `source_of_truth/standards/POINT_IN_TIME_AI_POLICY.md`

## Phase 3 rules

1. Search before creating new files.
2. Change only the minimum authoritative surface.
3. Reuse shared contracts and utilities.
4. Update manifests, hashes and rollback evidence for every integration change.
5. Treat all external evidence as point-in-time and fail closed when authority is missing.
