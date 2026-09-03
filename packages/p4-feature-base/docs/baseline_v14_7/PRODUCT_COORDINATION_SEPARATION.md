# Product–Coordination Separation

`product_core/` is the complete technical specification of P4. It contains no implementation-team identifiers and must be sufficient to build, test, integrate and qualify the phase.

Rules:

- no worker, agent or branch identifier may appear in Python packages, imports, contracts, schemas, artifact fields, log fields, module IDs, feature IDs, error codes or runtime configuration;
- technical ownership is expressed only through producer module IDs and contract authorities;
- deleting `coordination_only/` must not change product schemas, hashes inside the product manifest, importability, test behavior or P4 outputs;
- `coordination_only/` may describe temporary work allocation, branch paths and merge order, but may not redefine a product contract;
- domain data names such as `agent_disagreement_panel` are permitted because they describe P3 simulation data, not implementation workers.
