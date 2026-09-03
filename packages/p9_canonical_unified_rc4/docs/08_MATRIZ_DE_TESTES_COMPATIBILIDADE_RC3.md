# Matriz de testes de compatibilidade

| Caso | Prova |
|---|---|
| P8 nativa → P9 LIMITED | 20 artefatos aceitos por S1 |
| P8 nativa falsamente FULL | rejeitada |
| P8 + suplementos → P9 FULL | 26 artefatos e `ACCEPTED_FULL` |
| candidatos P8 divergentes | rejeitados |
| feedback P9/P0 → modelo P8 | validação pelo TypeAdapter real |
| feedback → loader P8 | `APPLIED`, depois `ALREADY_APPLIED` |
| source cycle ausente | rejeitado |
| datetime ingênuo | rejeitado |
| P3 S31 → P9 | modelo e manifest reais |
| P9 → belief consumer P3 | aceito |
| P9 → retro consumer P3 | `NO_PATCH`, sem mutação direta |
| P5/P7/P8 RC4.1 | reports aceitos pelos consumers reais |
| P6 RC4.1 | ausência de consumer direto confirmada |
| P0 reports | normalização e schema reais |
| P0–P8 snapshots | 9 fingerprints SHA-256 verificados |
| isolamento científico | AST sem imports de P0–P8 |
| regressão P9 | 591 testes PASS |
| regressão P8 coinstalada | 631 testes PASS |
