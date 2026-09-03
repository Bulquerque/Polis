# Contract Reconciliation Record

## Foundation and economic workstreams

Resolved differences:

- rich typed values versus a generic `value` field;
- theory-rich observer registry versus execution-routing registry;
- quality state `VALIDATED` versus `PASS`;
- duplicated operator execution between S3 and S4.

Decision:

- the typed S2 store is canonical;
- S4 receives a projection, not a replacement store;
- S3 owns theory, authorization and generic operators;
- S4 owns domain materialization;
- the execution registry is compiled from approved S3 hypotheses.

## Economic and downstream workstreams

Resolved differences:

- `value` versus `feature_value`;
- absent family/perspective/parameterization metadata;
- lost `available_at` in composite features;
- incompatible lineage names and quality vocabulary.

Decision:

- S7 receives a superset record with explicit economic identity and temporal lineage;
- composite availability is the maximum of all parent availabilities;
- no manual field-renaming adapters are allowed outside the canonical adapter.

## Additional corrections found by integrated execution

- historical raw records now support record-specific decision times;
- derived feature IDs are mapped to actual atomic operators;
- all-missing and constant PCA columns no longer create NaN fit states;
- stateless S7 transforms are valid in S9 without fake fit timestamps;
- S9 does not accept null causal timestamps for stateful transforms.
