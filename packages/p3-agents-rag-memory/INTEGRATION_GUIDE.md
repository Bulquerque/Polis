# Phase 3 integration guide

## Purpose

Integrate the Phase 3 package into the full repository without accepting stale schemas, synthetic qualification, unsigned downstream consumption or self-promotion.

## 1. Verify the package

```bash
python tools/release.py validate
python -m quant_pipeline.phase_03_agents_rag_memory.orchestration.cli doctor
```

The validation must report 128 executable modules, preserve the 81-module legacy registry, match schema mirrors, match contract mirrors, validate the S16 MCP v2 schema binding, report valid documentation links and contain no transient files.

## 2. Migrate the repository

```bash
python integration/new_version_sanitized/apply_authority_and_runtime_migration.py plan --repository-root <NEW_VERSION_ROOT>
python integration/new_version_sanitized/apply_authority_and_runtime_migration.py apply --repository-root <NEW_VERSION_ROOT>
python integration/new_version_sanitized/apply_authority_and_runtime_migration.py validate --repository-root <NEW_VERSION_ROOT>
```

The migrator backs up every changed file outside the repository tree, regenerates repository manifests and supports byte-for-byte rollback. Keep the reported backup path.

## 3. Install Phase 3

```bash
python integration/new_version_sanitized/install_phase3.py plan --repository-root <NEW_VERSION_ROOT>
python integration/new_version_sanitized/install_phase3.py apply --repository-root <NEW_VERSION_ROOT>
python integration/new_version_sanitized/install_phase3.py validate --repository-root <NEW_VERSION_ROOT>
```

## 4. Configure authority keys

Use separate Ed25519 keys for P0, P2, P3 runtime, P4, P9 and operations. Never reuse a private key across authorities. The keyring contains public keys only. See `integration/final/KEY_MANAGEMENT.md`.

## 5. Execute the real pipeline

```bash
p3 run-pipeline-real \
  --driver company_package.phase3_driver:create_driver \
  --config integration-config.json \
  --keyring authority-keyring.json \
  --output-dir run-output
```

The driver must execute the 81 canonical production modules, write a complete trace, reload the checkpoint in a new process, execute the next cycle and return signed runtime receipts. The 47 research-tools modules are an additive internal execution plane and are qualified through their own registry, contracts, gateway and receipts. Test adapters and generated observations are not qualification evidence.

The S16 `MCPGatewayPolicy` v2 artifact is projected into the smaller S21 runtime
policy only through `extensions/research_tools/compatibility/s21_gateway_policy.py`.
External MCP remains optional and disabled unless an independently configured
provider receipt authorizes it; backtest and replay remain network-free.

For a single consolidated research-tools execution, use the dedicated runner:

```bash
p3 research-tools-run \
  --driver company_package.research_tools_driver:create_driver \
  --config research-tools-run.json \
  --output run-output/research-tools-receipt.json
```

The driver must expose `prepare(config, output_dir)` and return one mapping with
`gateway`, `requests`, `run_id`, `cycle_id`, `decision_time` and `snapshot_id`.
The runner dispatches the complete batch sequentially through the one composite
gateway and writes one content-addressed receipt. A failed operation is retained
in that receipt and changes the batch status to `FAIL`; it is never converted into
a synthetic success.

## 6. Prepare integration evidence

```bash
p3 integration-init --output-dir evidence
p3 integration-run --driver company_package.evidence_driver:create_driver --config integration-config.json --output-dir evidence
```

Populate every template with evidence from the exact release hash. P4 and P9 must sign receipts for the exact artifacts they consumed.

## 7. Qualify

```bash
p3 integration-qualify --evidence-dir evidence --keyring authority-keyring.json --output integration-report.json
```

All gates must pass in order: intake, data, calibration, experiment, science, cross-phase consumption, quality and P0 promotion.

## 8. Build the promotion candidate

```bash
p3 integration-build-candidate --evidence-dir evidence --keyring authority-keyring.json --output promotion-candidate.json
```

P3 creates only the candidate. P0 independently verifies it and is the only authority allowed to sign the promotion decision.

## Rollback

Use the exact backup path returned by the migration or installer:

```bash
python integration/new_version_sanitized/install_phase3.py rollback --repository-root <NEW_VERSION_ROOT> --backup <BACKUP_PATH>
python integration/new_version_sanitized/apply_authority_and_runtime_migration.py rollback --repository-root <NEW_VERSION_ROOT> --backup <BACKUP_PATH>
```

After rollback, regenerate and verify all repository manifests and invalidate downstream receipts that reference the reverted release hash.
