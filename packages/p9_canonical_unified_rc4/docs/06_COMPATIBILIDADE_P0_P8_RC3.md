# Compatibilidade P0–P8 — RC3

## Princípio

A P9 não incorpora implementações das fases anteriores e não converte contratos com `model_dump()` genérico. Cada fronteira possui uma autoridade explícita, um perfil de canonicalização, clocks, hashes e um estado de capacidade.

## Matriz

| Fase | Evidência executável | Resultado |
|---|---|---|
| P0 | `normalize_family`, `source_control` e schema de dashboard reais | PASS |
| P1 | SHA-256 do `MANIFESTO.csv` qualificado | PASS |
| P2 | SHA-256 do `MANIFESTO.csv` qualificado | PASS |
| P3 | modelos S31 e consumers de belief/retro em subprocesso | PASS |
| P4 | SHA-256 do `MANIFESTO.csv` qualificado | PASS |
| P5 | consumer `P5.S1.M02` real | PASS |
| P6 | contrato confirma `optional_feedback_inputs: []` | GOVERNED |
| P7 | consumer `P7.S1.M02` real | PASS |
| P8 | publisher nativo, S1 da P9 e loader `P8.S1.M04` real | PASS/LIMITED |

## Estados

- `COMPATIBLE`: contrato e consumer qualificados sem limitação material.
- `COMPATIBLE_LIMITED`: o wire contract funciona, mas o produtor não publica toda a evidência necessária para FULL.
- `COMPATIBLE_PROCESS_ISOLATED`: compatível através de uma fronteira de processo devido ao namespace legado.
- `COMPATIBLE_GOVERNED`: a fase não possui consumer direto e a ativação é mediada pela P0.

## Regras de segurança

1. Nenhum adapter fabrica evidência ausente.
2. Identidades de run, ciclo, backtest e configuração são preservadas.
3. Hashes são recalculados pelo perfil do consumidor.
4. Feedback só pode atingir um ciclo posterior.
5. A P0 é a única autoridade que transforma recomendação em mudança ativa.
6. O modo FULL da P8 exige suplementos com schema Draft 2020-12 e cardinalidade coerente.
