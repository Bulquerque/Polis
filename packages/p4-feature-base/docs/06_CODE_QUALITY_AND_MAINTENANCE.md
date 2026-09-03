# Code Quality and Maintenance Standard

## Design rules

- Module wrappers remain thin and delegate to domain services.
- Temporal, lineage and quality metadata are never created with silent defaults.
- Missing data is represented by explicit states, not numeric zero.
- Any fit state records its training interval and must precede its transformed records.
- The encoder is optional and cannot block the selected-feature/PCA path.
- No target, realized return, candidate, portfolio weight or P&L field may enter P4.

## Size budgets

These are engineering guardrails, not incentives to split cohesive code artificially:

- hard Python file size: at most 350 lines;
- hard function size: at most 60 lines;
- hard class size: at most 180 lines;
- module wrapper file: at most 60 lines;
- module wrapper function: at most 40 lines.

The release validator rejects every hard-limit violation; exceptions are not accepted in a promotable tree. Ruff uses a 100-character soft line-length target when the optional quality toolchain is available. Line width is a readability signal, while the release-blocking complexity budgets are file, function, class and wrapper size.

## Navigation

- `boundary/` and `temporal/`: upstream validity and point-in-time authority.
- `observers/`: hypothesis governance, DSL and reusable operators.
- `atomic/`: source-modality observations.
- `perspectives/`: economic interpretation families.
- `fusion/`: alignment, conflict and interactions.
- `s7/`, `s8/`, `s9/`: downstream transforms, representations and assurance.
- `adapters/`: the only legal translations between independently evolved subphase contracts.

## Debugging discipline

1. Reproduce with a minimal domain fixture.
2. Validate the artifact envelope and schema before inspecting formulas.
3. Trace `decision_time`, `available_at` and lineage through parent records.
4. Run the relevant subphase test.
5. Run the integrated S1→S9 regression.
6. Regenerate the manifest only after all checks pass.
