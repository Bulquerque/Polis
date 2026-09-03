# Contract Registry

Os contratos externos originais permanecem em seus pacotes canônicos. Esta pasta documenta a composição integrada e não cria uma segunda implementação.

## Fronteiras

- S1/S2 → S3/S4: `A1ToA2Context` + contracts S1/S2/S3/S4
- S3/S4 → S5/S6: `A2ToA3Context` + `DecisionReadyRiskBundle` + `RiskLifecycleContextBundle`
- S5/S6 → S7/S8: `P8ExecutionAuthorizationBundle`
- S7/S8 → S9/S10: `StatefulEvidenceBundle`
- S9 → S7/S8: `RuntimeControlCommand`

Schemas derivados estão em `schemas/generated/`. A autoridade executável é sempre o model importado da árvore `src/`.
