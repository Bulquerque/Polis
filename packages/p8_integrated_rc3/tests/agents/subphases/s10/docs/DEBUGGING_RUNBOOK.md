# Debugging runbook

1. Execute `p8-s10 audit <bundle.json>`.
2. Localize checks `FAIL` ou `WARNING` e seus reason codes.
3. Compare `expected_value`, `observed_value` e `residual`.
4. Verifique clocks, artifact hashes e candidate IDs antes de alterar lógica econômica.
5. Para replay, confira event sequence e `expected_state_sha256`.
6. Para qualification, separe falha técnica, robustez insuficiente e estatística insuficiente.
7. Nunca corrija o ledger dentro do auditor; corrija o produtor e execute novamente.
