# P5 RC34 → P6 RC6.1 Compatibility Matrix

## Veredito

| Dimensão | Estado |
|---|---|
| Schema compacto `market_belief_state` | PASS |
| Manifest V2 completo | PASS |
| Hash do manifest-pai | PASS |
| 11 referências, hashes e schemas | PASS |
| Run/cycle/decision-time reconciliation | PASS |
| Availability e lineage receipts | PASS |
| Return distribution → terminal-price scenarios | PASS |
| Scenario path → path-price scenarios | PASS quando horizonte coincide |
| Confidence, abstention, regime e OOD | PASS |
| Horizon → template/candidate identity | PASS |
| Bundle real RC34, default fail-closed | PASS / EMPTY_VALID |
| Bundle real RC34, override de pesquisa | PASS / non-empty |
| Ambiguity distributions completas | LIMITED — IDs/radius sem vetores |
| Dependence econômica multi-underlying | RESERVED |
| Volatility/path-risk indisponíveis upstream | PRESERVED AS UNAVAILABLE |
| V1 `underlying_forecast_panel` | DEPRECATED LIMITED ADAPTER |
| Qualificação produtiva | FAIL / NOT CLAIMED |

## Regras da fronteira nativa

A P6 exige `phase6_strategy_scenario_manifest` para qualquer artefato que se identifique como P5 V2 nativo. O manifest é verificado com o algoritmo de identidade da P5 RC34 e todos os artefatos referenciados precisam resolver por ID, hash, schema e contagem.

A ordem de construção de cenários é:

1. cenários nativos do `market_belief_state`;
2. `scenario_paths` com mesmo underlying e horizonte;
3. `return_distributions` com mesmo underlying e horizonte, ancoradas no spot PIT da P2;
4. `LIMITED/UNAVAILABLE`, sem cenário inventado.

## Capabilities consumidas

| Artefato | Uso atual |
|---|---|
| `market_belief_state` | fonte canônica de beliefs |
| `return_distributions` | fonte de cenários quando o compact belief está vazio |
| `scenario_paths` | fonte de trajetórias quando o horizonte coincide |
| `forecast_confidence` | confidence, calibration e abstention |
| `regime_ood_states` | regime context, severity e reason codes |
| `ambiguity_sets` | metadata/radius/IDs preservados; vetores não reconstruídos |
| `availability_report` | receipts e fail-closed status |
| `lineage_report` | reconciliação de IDs, lineage e producer |
| `volatility_distributions` | validada e reservada para valuation; pode estar indisponível |
| `path_risk_forecasts` | validada e reservada; pode estar indisponível |
| `dependence_states` | validada e reservada para multi-underlying |

## Abstention

`allow_abstained_beliefs=false` é o default. Um belief abstido não participa do template plan, mesmo que uma distribuição possa ser convertida em cenários. O override existe somente para pesquisa e fica registrado na configuração da run.

## Legado V1

O adapter V1 aceita os campos reais RC34 (`underlying`, `prediction_timestamp`/`as_of_time`, `horizon`, `confidence`) e nunca fabrica cenários, ambiguity ou surface. Ele permanece depreciado e produz capability `LIMITED`.
