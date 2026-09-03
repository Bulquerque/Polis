# Start here

1. Read `INTEGRATION_GUIDE.md`.
2. Run `python tools/release.py validate`.
3. Apply the repository migration with `integration/new_version_sanitized/apply_authority_and_runtime_migration.py`.
4. Install Phase 3 with `integration/new_version_sanitized/install_phase3.py`.
5. Execute the production driver through `p3 run-pipeline-real`.
6. Collect signed evidence and run `p3 integration-qualify`.
7. Submit the immutable candidate to P0.

Production remains blocked until every external receipt and the P0 decision are valid.
