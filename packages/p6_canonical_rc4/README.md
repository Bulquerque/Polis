# P6 — Payoff Design, Strategy Synthesis and Candidate Generation

Release: **P6-RC6.2-P5-V2-CLOSURE-RC4**  
Package version: **0.6.2rc4**  
Schema version: **6.2.0-rc2**

A P6 compila crenças probabilísticas e snapshots point-in-time em estratégias negociáveis, multi-leg, determinísticas e auditáveis. Ela gera, avalia, qualifica, canonicaliza e publica candidatos para a P7, sem realizar ranking final, sizing, execução ou aprendizado retrospectivo.

## Compatibilidade nativa com P5 V2/RC34

A fronteira `P6.S1.M01` agora aceita e valida o bundle completo da P5 V2/RC34:

- `phase6_strategy_scenario_manifest`;
- `market_belief_state`;
- `return_distributions`;
- `volatility_distributions`;
- `path_risk_forecasts`;
- `scenario_paths`;
- `ambiguity_sets`;
- `dependence_states`;
- `regime_ood_states`;
- `forecast_confidence`;
- `availability_report`;
- `lineage_report`.

A validação inclui o hash do manifest-pai, IDs/hashes/schemas/contagens dos onze artefatos, identidade de run/cycle/decision time, availability, lineage e temporalidade. A P6 converte distribuições de retorno ou trajetórias compatíveis em cenários de preço usando exclusivamente o spot PIT da P2.

A execução real da fixture RC34 é fail-closed: os três beliefs estão em abstention, portanto o modo padrão publica universo `EMPTY_VALID`. Um override de pesquisa, explícito e auditável (`p5.allow_abstained_beliefs=true`), comprova o fluxo não vazio sem alterar o bundle upstream.

## Validação desta release

- 10 subfases e 55 módulos oficiais;
- 5 modos operacionais;
- 91 testes aprovados;
- 99,11% de statements e 95,60% de branches;
- bundle P5 V2/RC34 real incluído como golden fixture;
- replay determinístico;
- contracts, schemas, wheel, CLI e hashes validados;
- instalação conjunta com o wheel P5 V2/RC34 validada nas duas ordens;
- `production_promotion_allowed = false`.

## Execução

```bash
python -m pytest -q
python -m coverage run --branch -m pytest -q
python -m coverage report -m
PYTHONPATH=src python tools/validate_contracts.py
PYTHONPATH=src python tools/quality_gate.py
p6 --inputs inputs.json --configuration configuration.json --output result.json
```

## Limitações honestas

A integração estrutural e operacional da fronteira RC34 está qualificada. Permanecem limitados ou reservados:

- ambiguity sets da P5 contêm IDs/radius, mas não vetores alternativos completos;
- volatility distributions e path-risk forecasts podem estar `UNAVAILABLE` na P5;
- dependence é validada e preservada, mas só será economicamente utilizada em síntese multi-underlying;
- a fixture real abstém por baixa confiança/OOD severo;
- margem real, execução calibrada, chain de provider e qualificação econômica final da P7 continua externa ao fechamento técnico.

Esta release não transforma ausência upstream em zero, cenário fictício ou aprovação silenciosa.
