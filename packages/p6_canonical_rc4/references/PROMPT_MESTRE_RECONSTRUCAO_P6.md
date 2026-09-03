# PROMPT-MESTRE — RECONSTRUÇÃO ECONÔMICA, SEMÂNTICA E OPERACIONAL DA P6

## P6 — Payoff Design, Strategy Synthesis and Candidate Generation Engine

Você é o agente principal responsável por auditar, corrigir, redesenhar, implementar, testar, qualificar e empacotar a nova versão da **Fase 6 — Candidate Generation**, transformando-a em uma fase rigorosa de:

```text
estado de mercado point-in-time
→ desenho de payoff
→ construção de estratégias multi-leg
→ avaliação por cenários
→ controle de viabilidade
→ canonicalização
→ diversidade
→ publicação para ranking
```

A nova P6 deve conseguir gerar:

* posições simples em underlying;
* calls e puts isoladas;
* spreads verticais;
* straddles;
* strangles;
* butterflies;
* iron butterflies;
* condors;
* iron condors;
* calendars;
* diagonals;
* collars;
* risk reversals;
* ratio spreads com risco controlado;
* estruturas deformadas;
* estruturas assimétricas;
* estruturas com underlying overlay;
* estruturas sem nome tradicional;
* combinações obtidas por otimização inversa de payoff.

Entretanto, ela não deve transformar sofisticação em descontrole.

Toda estrutura deve ser:

```text
real
observável
temporalmente válida
negociável
economicamente identificável
reproduzível
avaliada sob cenários
limitada por risco
auditável
```

A P6 não deve criar score final, ranking, pesos de carteira, decisões de execução ou aprendizado retrospectivo.

---

# 1. BASELINE E PROTOCOLO DE INÍCIO

A baseline candidata mais recente é:

```text
P6_COMPLETE_S1_S6_INTEGRATED_RC5_9.zip
```

SHA-256 esperado:

```text
36ab1005d8cf97c44aef7c95e3bdbc20edb7a266dc74132888ef1d76dc5eec3e
```

Não confie apenas no nome ou no checksum armazenado.

Antes de modificar qualquer arquivo:

1. Localize o ZIP exato.
2. Calcule o SHA-256 dos bytes reais.
3. Compare com o checksum esperado.
4. Extraia em diretório novo e vazio.
5. Não reutilize pastas contendo `.pytest_cache`, `__pycache__` ou artefatos de execuções anteriores.
6. Inventarie:

   * subfases;
   * módulos;
   * contracts;
   * schemas;
   * serviços;
   * runners;
   * registries;
   * testes;
   * fixtures;
   * ferramentas;
   * outputs;
   * handoffs.
7. Execute todos os testes existentes antes de editar.
8. Registre:

   * testes aprovados;
   * testes falhos;
   * testes travados;
   * duração;
   * memória;
   * arquivos gerados;
   * mutações do workspace.
9. Compare a release RC5.9 com a P6 antiga presente na root P0–P9.
10. Produza um relatório de baseline chamado:

```text
P6_BASELINE_DEEP_AUDIT.md
```

O relatório deve separar:

```text
documentação declarada
implementação real
testes reais
contratos reais
validade econômica
compatibilidade real
dívida técnica
```

Não declare que a RC5.9 possui determinado número de módulos ou determinada funcionalidade antes de ler seus registries e código.

---

# 2. OBJETIVO CENTRAL

A nova P6 deve responder:

```text
Dadas as crenças probabilísticas da P5,
os instrumentos realmente existentes no instante t,
os custos, a liquidez, as regras contratuais e os limites de risco:

quais estruturas negociáveis expressam essas crenças?

como cada estrutura se comporta nos cenários?

quais são tecnicamente válidas?

quais são economicamente diferentes?

quais devem seguir para a P7?
```

A P6 não deve responder:

```text
qual estrutura é a melhor?
qual candidato deve ficar em primeiro?
quanto capital deve ser alocado?
qual ordem deve ser enviada?
quando a posição deve ser fechada?
o modelo teve alpha?
```

Essas responsabilidades pertencem a:

```text
P7 — ranking
P8 — carteira, sizing, execução e gestão
P9 — avaliação e aprendizado
```

---

# 3. STORYTELLING DA NOVA PIPELINE

A arquitetura deve respeitar:

```text
P5:
“Estes são os estados futuros plausíveis,
suas probabilidades,
dependências,
trajetórias,
incerteza,
regimes
e ambiguity sets.”

P6:
“Estes são os payoffs e estruturas negociáveis
que expressam essas crenças,
com estes custos,
riscos,
Greeks
e resultados por cenário.”

P7:
“Entre as estruturas válidas,
estas são preferíveis segundo edge,
risco,
robustez,
execução,
confiança
e diversidade.”

P8:
“Estas estruturas serão combinadas,
dimensionadas,
executadas
e administradas desta maneira.”

P9:
“O erro ou acerto veio da previsão,
geração,
ranking,
carteira,
execução
ou gestão.”
```

A P6 é um **compilador de crenças em payoffs negociáveis**.

Não é uma biblioteca de nomes de estratégias.

---

# 4. ESCOPO PERMITIDO

Você pode modificar:

```text
src/quant_pipeline/phase_06_candidate_generation/
tests relacionados à P6
contracts da P6
schemas da P6
registries da P6
configs da P6
fixtures da P6
tools de validação específicos da P6
qualification da P6
documentação da P6
package metadata da P6
```

Você pode produzir change sets separados para:

```text
P0 module registry
P0 contract registry
P0 schema registry
P0 topology
P5→P6 handoff
P6→P7 handoff
```

Não edite silenciosamente outras fases.

---

# 5. ESCOPO PROIBIDO

Não modifique o código econômico de:

```text
P1
P2
P3
P4
P5
P7
P8
P9
```

Não faça forecasting dentro da P6.

Não recalcule crenças da P5 com dados próprios.

Não crie features históricas que pertencem à P4.

Não escolha estratégias usando resultados futuros.

Não faça ranking.

Não monte carteira.

Não determine peso financeiro final.

Não simule execução completa da P8.

Não aplique feedback da P9 do ciclo corrente.

Não invente:

* contratos;
* strikes;
* vencimentos;
* quotes;
* bids;
* asks;
* volumes;
* open interest;
* custos;
* margens;
* regras de exercício;
* liquidez;
* preços;
* implied volatility;
* Greeks;
* probabilidades;
* disponibilidade temporal.

---

# 6. PRINCÍPIOS NÃO NEGOCIÁVEIS

## 6.1 Contrato real ou ausência explícita

Uma perna de opção somente pode existir se houver evidência point-in-time de:

```text
contract_id
underlying
option_type
strike
expiration
multiplier
exercise_style
settlement_type
valid_from
valid_until
```

Quando algum dado obrigatório não existir:

```text
UNAVAILABLE
REJECTED
BLOCKED
DEGRADED
SKIPPED
```

Nunca fabrique um contrato substituto.

---

## 6.2 Point-in-time

Toda informação consumida deve satisfazer:

```text
available_at <= decision_time
```

Todo contrato deve satisfazer:

```text
contract_valid_at(decision_time) = true
```

Toda quote deve satisfazer:

```text
quote_time <= decision_time
quote_available_at <= decision_time
```

Toda previsão deve satisfazer:

```text
forecast_created_at <= decision_time
model_trained_at <= decision_time
forecast_available_at <= decision_time
```

Uma linha futura adicionada ao dataset não pode alterar candidatos do passado.

---

## 6.3 Separação entre preço, valor e expectativa

Preserve conceitos distintos:

```text
market price
entry cost
mark value
model-implied expected payoff
risk-neutral expectation
physical expectation
utility
margin
maximum loss
```

Não use um como sinônimo do outro.

Não trate preço de mercado como probabilidade física.

Não trate expected payoff como valor justo automaticamente.

---

## 6.4 Sem arbitragem e sem reparo silencioso

A P6 deve detectar violações de:

* preços negativos;
* bounds básicos;
* monotonicidade de calls por strike;
* convexidade por strike;
* paridade put-call quando os inputs necessários existirem;
* calendar consistency;
* vertical spread bounds;
* butterfly consistency;
* quotes cruzadas;
* bid acima de ask;
* intrinsic bounds.

Se os dados violarem não arbitragem:

```text
REJECTED_RAW_MARKET_INCONSISTENCY
```

ou:

```text
REPAIRED_BY_EXPLICIT_POLICY
```

Reparo só pode ocorrer se:

* o método estiver habilitado;
* houver contract próprio;
* o dado original for preservado;
* a magnitude do reparo for publicada;
* o candidato indicar que usa dados reparados;
* a P7 puder penalizar essa condição.

Nunca altere quotes silenciosamente.

---

## 6.5 Risco definido por padrão

Na primeira baseline operacional:

```text
naked short options = proibido
undefined maximum loss = proibido
unbounded liability = proibido
```

Pernas vendidas somente são permitidas quando a estrutura completa prova:

```text
maximum_loss finite
margin estimate available
payoff bounded below
all protective legs present
```

Exemplos inicialmente permitidos:

* vertical credit spread;
* iron condor;
* iron butterfly;
* butterfly;
* broken-wing com perda finita;
* collar;
* ratio spread protegido.

Exemplos inicialmente bloqueados:

* naked short call;
* naked short put sem collateral model;
* ratio spread com cauda ilimitada;
* combinação cujo max loss não possa ser provado.

---

## 6.6 Honestidade sobre margem

A P6 não deve fingir conhecer margem exata quando não conhece regras da corretora ou clearing.

Produza:

```text
margin_estimate
margin_method
margin_scope
margin_confidence
margin_status
```

Métodos possíveis:

```text
EXACT_RULE_ENGINE
DEFINED_RISK_UPPER_BOUND
CONSERVATIVE_PROXY
UNAVAILABLE
```

A P8 decide uso efetivo de capital e buying power.

---

## 6.7 Não ranking

A P6 pode:

* bloquear inválidos;
* remover duplicados;
* manter arquivos de qualidade-diversidade;
* eliminar equivalentes estritamente piores por razões técnicas;
* aplicar budgets de geração.

A P6 não pode produzir:

```text
rank = 1
best_candidate
recommended_trade
portfolio_weight
selection_decision
```

O quality-diversity archive é uma ferramenta de cobertura do espaço, não um ranking final.

---

## 6.8 Determinismo

Com os mesmos:

```text
market snapshot hash
P5 belief hashes
config
seed
solver version
solver settings
calendar version
```

a geração deve produzir os mesmos candidatos e hashes.

Se um solver não for determinístico:

* fixe seed;
* fixe thread count quando necessário;
* registre tolerâncias;
* publique status;
* teste equivalência econômica.

---

## 6.9 Complexidade controlada

Não enumere o produto cartesiano inteiro de:

```text
strikes
expirations
option types
sides
quantities
legs
```

Implemente budgets e poda.

Todo modo deve declarar:

```text
max_contracts_considered
max_templates
max_mutations
max_legs
max_expirations
max_quantity
max_solver_seconds
max_memory
max_candidates_before_dedup
max_candidates_published
```

---

## 6.10 CPU-first

O caminho canônico deve funcionar sem:

* GPU;
* serviço pago;
* solver comercial obrigatório;
* rede;
* modelo externo.

Solvers comerciais podem existir como adapters opcionais, nunca como requisito.

---

## 6.11 Ausência não é zero

Proibido:

```python
liquidity = 0.0
margin = 0.0
cost = 0.0
iv = 0.0
delta = 0.0
```

quando o valor está ausente.

Use:

```text
value = null
status = UNAVAILABLE
reason_code = ...
```

Zero é um valor econômico válido e deve ser distinguido de ausência.

---

## 6.12 Sem mutação dos inputs

Nenhum módulo pode alterar in-place:

* cenários P5;
* option chain P2;
* forecasts;
* contracts;
* quotes;
* configs;
* artifacts.

---

# 7. DECISÃO ARQUITETURAL

A RC5.9 deve ser auditada antes de definir se os seis IDs de subfase podem ser preservados.

A arquitetura-alvo contém dez responsabilidades econômicas:

```text
A. intake e snapshot
B. representação canônica
C. templates
D. deformação/mutação
E. target payoff
F. inverse design
G. avaliação por cenários
H. feasibility e risco
I. canonicalização e diversidade
J. publicação
```

Existem duas opções aceitáveis.

## Opção 1 — Expandir formalmente para dez subfases

Use quando a RC5.9 ainda não possui contracts públicos estabilizados e quando a expansão melhora claramente:

* ownership;
* testes;
* navegação;
* gates;
* paralelização;
* isolamento.

Topologia:

```text
P6.S1 — Boundary and Market Snapshot
P6.S2 — Canonical Strategy Domain
P6.S3 — Template Generation
P6.S4 — Mutation and Deformation
P6.S5 — Target Payoff and Inverse Design
P6.S6 — Pricing, Greeks and Scenario Evaluation
P6.S7 — Feasibility and Defined-Risk Gate
P6.S8 — Canonicalization and Equivalence
P6.S9 — Quality-Diversity Archive
P6.S10 — Publication and P7 Handoff
```

## Opção 2 — Preservar seis subfases e criar módulos internos bem separados

Use somente se:

* IDs S1–S6 já forem contratos congelados;
* compatibilidade externa for material;
* cada responsabilidade continuar legível;
* não surgir subfase monolítica;
* ownership permanecer claro.

Uma possível composição:

```text
P6.S1 — Intake and Snapshot
P6.S2 — Canonical Domain and Feasibility Foundations
P6.S3 — Templates and Mutation
P6.S4 — Target Payoff and Inverse Design
P6.S5 — Scenario Evaluation, Canonicalization and Diversity
P6.S6 — Qualification and Publication
```

Antes de escolher, produza:

```text
P6_SUBPHASE_ARCHITECTURE_DECISION.md
```

O documento deve comparar:

* backward compatibility;
* quantidade real de módulos;
* risco de monólito;
* ownership;
* contratos;
* complexidade;
* migração;
* impacto P0;
* impacto P7.

Não expanda por estética.

Não preserve por medo quando a arquitetura ficar incoerente.

---

# 8. DOMÍNIO CANÔNICO

Implemente um único domínio canônico.

Não crie modelos duplicados em engines privadas.

## 8.1 `InstrumentReference`

```text
instrument_id
instrument_type
underlying_id
currency
exchange
multiplier
valid_from
valid_until
source_artifact_id
source_record_id
```

## 8.2 `OptionContractReference`

```text
contract_id
underlying_id
option_type
strike
expiration
exercise_style
settlement_type
multiplier
currency
listing_exchange
first_trade_date
last_trade_date
contract_status
```

## 8.3 `ExecutableQuote`

```text
contract_id
quote_time
available_at
bid
ask
bid_size
ask_size
last
last_size
volume
open_interest
quote_quality
source_id
```

Não use automaticamente `last` como preço executável.

## 8.4 `StrategyLeg`

```text
leg_id
instrument_id
instrument_type
side
quantity
option_type
strike
expiration
multiplier
entry_price_reference
price_selection_method
leg_role
```

`leg_role` pode ser:

```text
CORE
FINANCING
PROTECTION
DIRECTIONAL_OVERLAY
VOLATILITY_OVERLAY
TAIL_HEDGE
```

## 8.5 `StrategyCandidate`

```text
candidate_id
candidate_version
underlying_id
decision_time
horizon
objective_family
origin_mode
origin_template_id
parent_candidate_ids
mutation_trace
legs
strategy_scale
entry_cash_flow
maximum_loss
maximum_gain
margin_estimate
payoff_fingerprint
economic_fingerprint
generation_run_id
lineage_id
```

## 8.6 `TargetPayoff`

```text
target_payoff_id
underlying_id
decision_time
horizon
objective_family
terminal_state_grid
desired_payoff
desired_wealth_distribution
path_constraints
tail_constraints
cost_budget
risk_budget
complexity_budget
belief_state_id
ambiguity_set_id
```

## 8.7 `ScenarioEvaluation`

```text
candidate_id
scenario_id
scenario_probability
terminal_payoff
pathwise_mark_to_market
maximum_path_loss
margin_stress
liquidity_stress
exercise_state
assignment_state
scenario_cost
scenario_pnl
```

## 8.8 `CandidateRiskSummary`

```text
expected_net_payoff
median_net_payoff
probability_of_profit
lower_quantiles
upper_quantiles
value_at_risk
expected_shortfall
maximum_loss
maximum_gain
return_on_max_loss
return_on_margin
break_even_points
profit_region_measure
loss_region_measure
payoff_asymmetry
nominal_utility
worst_ambiguity_utility
regret
```

## 8.9 `GreekState`

```text
delta
gamma
vega
theta
rho
vanna
volga
charm
calculation_method
calculation_time
input_surface_id
status
```

Não exija todos os Greeks em todos os modos.

Os obrigatórios iniciais podem ser:

```text
delta
gamma
vega
theta
```

Greeks superiores devem ser capability opcional.

## 8.10 `CandidateGenerationTrace`

```text
candidate_id
origin
parents
operators
parameters
solver_id
solver_status
generation_stage
rejection_history
dedup_cluster
```

---

# 9. ARTIFACT ENVELOPE E RECORD SCHEMAS

Separe sempre:

```text
artifact envelope
record schema
```

O envelope deve conter:

```text
artifact_id
artifact_type
schema_version
producer_phase
producer_module_id
run_id
cycle_id
decision_time
created_at
available_at
content_sha256
record_count
lineage_id
records
```

Não copie campos econômicos do primeiro record para o envelope.

Todos os outputs devem ser validados em runtime.

---

# 10. INTERFACE P5→P6

A P6 deve aceitar a nova visão V2 da P5.

Inputs canônicos esperados:

```text
market_belief_state
return_distribution_panel
volatility_distribution_panel
path_risk_forecast_panel
scenario_path_panel
ambiguity_set
dependence_state
regime_ood_state
forecast_confidence_panel
phase6_strategy_scenario_manifest
```

A P6 também consome diretamente da P2:

```text
clean_option_contract_panel
clean_option_quotes_panel
clean_underlying_trade_panel
clean_calendar_panel
clean_cost_reference_panel
clean_liquidity_reference_panel
phase6_handoff_manifest
```

## Compatibility adapter

Durante a migração, aceite:

```text
underlying_forecast_panel V1
```

somente por um adapter explícito:

```text
P5ForecastV1Adapter
```

A projeção V1 deve receber capability limitada:

```text
scenario_capability = LIMITED
ambiguity_capability = UNAVAILABLE
surface_capability = UNAVAILABLE
```

Nunca invente os outputs V2 ausentes.

## Reconciliation

Valide entre P5 e P2:

```text
underlying_id
decision_time
calendar
currency
horizon
universe
contract snapshot
```

P5 não pode referenciar underlying ausente no snapshot da P2.

---

# 11. P6.S1 — BOUNDARY E MARKET SNAPSHOT

## P6.S1.M01 — P5 belief handoff validator

Valide:

* manifest;
* hashes;
* schema;
* grain;
* decision time;
* forecast cutoff;
* model training time;
* availability;
* scenario mass;
* finite values;
* dependence ordering;
* confidence status;
* ambiguity status;
* future-field leakage.

Rejeite forecast gerado depois da decisão.

Não aceite apenas a presença de um nome de artifact.

## P6.S1.M02 — Option market input validator

Valide:

* contracts;
* quotes;
* calendar;
* cost references;
* liquidity;
* manifest;
* hash;
* temporalidade;
* duplicação;
* bid-ask;
* units;
* multiplier;
* currency;
* exercise style;
* settlement.

Não corrija economicamente aqui.

## P6.S1.M03 — Underlying market input validator

Valide:

* underlying price;
* quote/trade time;
* availability;
* currency;
* calendar;
* cost;
* liquidity;
* corporate-action state;
* trading status.

## P6.S1.M04 — Static arbitrage diagnostic

Crie um relatório de:

```text
intrinsic bound violations
negative price violations
bid-ask violations
vertical violations
butterfly violations
calendar violations
put-call parity diagnostics
```

Não bloqueie todo o universo por uma quote ruim isolada quando ela puder ser excluída com evidência.

## P6.S1.M05 — PIT market snapshot builder

Construa:

```text
StrategyMarketSnapshot
```

com:

* P5 belief references;
* option contracts;
* valid quotes;
* underlying;
* costs;
* liquidity;
* calendar;
* exact hashes;
* rejection report.

O snapshot deve ser imutável.

---

# 12. P6.S2 — CANONICAL STRATEGY DOMAIN

## P6.S2.M01 — Contract existence gate

Expanda o gate existente.

Verifique por perna:

```text
listed_at_decision_time
not_expired
not_delisted
quote_available
exercise_supported
settlement_supported
multiplier_known
currency_known
```

## P6.S2.M02 — Strategy grammar registry

Crie um registry declarativo de:

```text
primitives
templates
operators
constraints
objective families
risk classes
```

Não hardcode toda a gramática em `if/elif`.

## P6.S2.M03 — Objective family registry

Famílias iniciais:

```text
DIRECTIONAL_UP
DIRECTIONAL_DOWN
RANGE
LONG_VOLATILITY
SHORT_VOLATILITY_DEFINED_RISK
POSITIVE_CONVEXITY
TAIL_HEDGE
INCOME_DEFINED_RISK
SKEW_RELATIVE_VALUE
TERM_STRUCTURE
EVENT
PORTFOLIO_HEDGE
HYBRID
```

A família não é recomendação.

Ela define o tipo de payoff buscado.

## P6.S2.M04 — Constraint policy registry

Registre:

```text
max_legs
max_expirations
max_quantity
short_leg_policy
risk_definition
cost_budget
margin_budget
liquidity_minimum
spread_maximum
allowed_exercise_styles
allowed_settlement_types
```

## P6.S2.M05 — Strategy identity builder

O candidate ID deve depender do conteúdo canônico:

```text
underlying
decision_time
legs ordenadas
quantidades
objective family
generation policy version
```

Não dependa da ordem acidental de geração.

---

# 13. P6.S3 — TEMPLATE GENERATION

## P6.S3.M01 — Single instrument generator

Gere:

* underlying long/short quando autorizado;
* long call;
* long put;
* covered ou protective combinations quando todos os componentes existirem.

Não gere automaticamente short naked.

## P6.S3.M02 — Vertical generator

Gere:

```text
bull call spread
bear put spread
bull put credit spread
bear call credit spread
```

Credit spreads somente com max loss comprovado.

## P6.S3.M03 — Volatility structure generator

Gere:

```text
long straddle
long strangle
iron butterfly
iron condor
long butterfly
long condor
```

Short straddle e short strangle nus permanecem bloqueados.

## P6.S3.M04 — Skew and asymmetric generator

Gere:

```text
risk reversal
collar
broken-wing butterfly
asymmetric condor
protected ratio spread
```

## P6.S3.M05 — Term structure generator

Gere:

```text
calendar
diagonal
double calendar
defined-risk time spread
```

Somente quando:

* múltiplos vencimentos existirem;
* calendários forem consistentes;
* exercício antecipado e dividendos forem tratados ou explicitamente limitados.

## P6.S3.M06 — Underlying overlay generator

Permita overlay controlado:

```text
option structure
+
underlying quantity
```

A quantidade deve ser limitada e versionada.

Não transforme isso em hedge dinâmico; é uma posição estática inicial.

## P6.S3.M07 — Template parameter planner

Escolha grids de:

```text
moneyness
delta bucket
DTE bucket
wing width
center shift
quantity
expiration pair
```

Não use todos os strikes indiscriminadamente.

A seleção deve considerar:

* liquidez;
* distância;
* forecast horizon;
* objective family;
* budgets.

---

# 14. P6.S4 — MUTATION E DEFORMATION ENGINE

## P6.S4.M01 — Mutation operator registry

Operadores:

```text
SHIFT_CENTER
MOVE_STRIKE
WIDEN_LEFT_WING
WIDEN_RIGHT_WING
NARROW_LEFT_WING
NARROW_RIGHT_WING
CHANGE_QUANTITY
ADD_PROTECTION
REMOVE_REDUNDANT_LEG
REPLACE_LEG
CHANGE_EXPIRATION
ADD_UNDERLYING
REMOVE_UNDERLYING
SPLIT_QUANTITY
MERGE_IDENTICAL_LEGS
```

Cada operador deve declarar:

```text
preconditions
postconditions
risk_effect
complexity_cost
allowed_templates
maximum applications
```

## P6.S4.M02 — Local mutation engine

Aplique mutações a:

* melhores candidatos por cobertura técnica;
* representantes de templates;
* soluções próximas do target payoff;
* nichos pouco cobertos.

Não use rank econômico da P7.

Critérios locais podem ser:

```text
payoff approximation error
feasibility
uniqueness
coverage descriptor
```

## P6.S4.M03 — Mutation trace validator

Toda estratégia deformada precisa publicar genealogia completa.

Exemplo:

```text
origin_template = LONG_STRANGLE

mutations:
1. MOVE_PUT_STRIKE: 95 → 92
2. CHANGE_CALL_QUANTITY: 1 → 2
3. ADD_UNDERLYING: 0 → 0.10
```

## P6.S4.M04 — Complexity budget gate

Bloqueie crescimento explosivo.

Penalize ou rejeite:

* pernas redundantes;
* ciclos de mutação;
* adicionar e remover a mesma perna;
* estruturas economicamente equivalentes;
* excesso de expirações;
* quantity scaling sem mudança de forma.

---

# 15. P6.S5 — TARGET PAYOFF DESIGN

## P6.S5.M01 — Belief-to-payoff transformer

Transforme a crença da P5 em uma função desejada de payoff.

Modos:

```text
BELIEF_RATIO
EXPECTED_UTILITY
TARGET_DISTRIBUTION
TAIL_HEDGE
RANGE_EXPRESSION
SCENARIO_WEIGHTED
USER_POLICY
```

## BELIEF_RATIO

Quando existir uma distribuição física da P5 e uma distribuição implícita de mercado válida:

```text
raw_target(state) =
physical_density(state)
/
market_implied_density(state)
```

Mas nunca use a razão diretamente.

Aplique:

```text
epsilon regularization
power shrinkage
clipping
normalization
confidence shrinkage
OOD shrinkage
tail budget
cost budget
```

Se a densidade implícita não puder ser estimada com qualidade:

```text
mode_status = UNAVAILABLE
```

## EXPECTED_UTILITY

Permita funções de utilidade versionadas:

```text
CARA
CRRA
LOG_WITH_FLOOR
MEAN_CVAR
TARGET_SHORTFALL
```

Não escolha aversão ao risco arbitrariamente.

Parâmetros devem vir de config/policy.

## TARGET_DISTRIBUTION

Permita definir distribuição desejada de riqueza terminal ou payoff.

## TAIL_HEDGE

Produza payoff que priorize proteção em cenários extremos.

## RANGE_EXPRESSION

Produza payoff concentrado em faixa, com perdas limitadas.

## SCENARIO_WEIGHTED

Permita descrever payoff desejado diretamente na grade de cenários P5.

---

## P6.S5.M02 — Market-implied state estimator

Quando os dados permitirem:

* derive informação implícita da cadeia;
* preserve distinção entre (\mathbb P) e (\mathbb Q);
* publique método;
* publique smoothing;
* publique repair status;
* publique coverage de strikes;
* publique tail extrapolation status.

Não confunda densidade risk-neutral com previsão física.

---

## P6.S5.M03 — Target payoff regularizer

Controle:

* descontinuidades;
* caudas explosivas;
* concentração extrema;
* sensibilidade a poucos estados;
* payoff impossível;
* custo teórico excessivo.

Produza:

```text
raw_target_payoff
regularized_target_payoff
regularization_report
```

---

## P6.S5.M04 — Target payoff qualification gate

Valide:

* finitude;
* unidades;
* suporte;
* boundedness quando necessário;
* consistência com objective family;
* custo budget;
* tail constraints;
* ambiguity robustness;
* confiança mínima.

---

# 16. P6.S6 — INVERSE PAYOFF DESIGN

## P6.S6.M01 — Replication basis builder

Monte uma base com:

```text
cash
underlying
available calls
available puts
```

Somente instrumentos válidos e líquidos.

O basis deve registrar:

```text
instrument_id
payoff_vector
entry_cost
liquidity
margin proxy
```

## P6.S6.M02 — Continuous relaxation solver

Resolva uma aproximação contínua inicial:

[
\min_q
\sum_s w_s
\left(\Pi_q(s)-g^*(s)\right)^2
+
\lambda_C C(q)
+
\lambda_L L(q)
+
\lambda_K K(q)
]

Restrições:

```text
quantity bounds
cost budget
risk budget
leg budget
defined-risk
```

A solução contínua não é automaticamente negociável.

## P6.S6.M03 — Mixed-integer solver

Converta seleção de contratos e quantidades em problema discreto.

Suporte adapter para solver open-source.

Registre:

```text
solver_name
solver_version
status
objective
best_bound
optimality_gap
wall_time
node_count
timeout
```

Não declare ótimo quando houver timeout.

## P6.S6.M04 — Beam search solver

Implemente baseline determinística de busca combinatória.

Estados:

```text
partial strategy
remaining leg budget
current payoff
current cost
current risk
```

Poda por:

* lower bound;
* infeasibility;
* duplicate fingerprint;
* excessive cost;
* excessive risk;
* insufficient improvement.

## P6.S6.M05 — Local search solver

Operadores locais:

```text
add
remove
replace
move strike
change quantity
change expiration
```

## P6.S6.M06 — Evolutionary challenger

Somente challenger.

Requisitos:

* seed;
* bounded population;
* bounded generations;
* repair operator;
* feasibility-first selection;
* mutation trace;
* archive;
* deterministic replay dentro de tolerância.

## P6.S6.M07 — Solver portfolio orchestrator

Não confie em um único solver.

Modos:

```text
EXACT_FIRST
BEAM_FIRST
HYBRID
CHALLENGER
```

O solver portfolio deve preservar:

* melhor solução de cada método;
* status;
* tempo;
* diversidade;
* approximation error.

---

# 17. P6.S7 — PRICING, GREEKS E PAYOFF ENGINE

## P6.S7.M01 — Entry price engine

Modos:

```text
CONSERVATIVE
MID
MARK
BID_ASK
COMBO_QUOTE
```

Política inicial recomendada:

```text
long leg entry = ask ou modelo conservador
short leg entry = bid ou modelo conservador
```

Não use midpoint como verdade sem declarar.

Para estruturas multi-leg, publique:

* custo por perna;
* custo agregado;
* spread agregado;
* execução atômica disponível ou não.

## P6.S7.M02 — Terminal payoff engine

Calcule payoff terminal exato por contrato.

Trate:

* multiplier;
* quantity;
* call/put;
* long/short;
* cash flow inicial;
* underlying;
* settlement;
* expiration.

## P6.S7.M03 — Pathwise valuation engine

Quando a P5 fornecer trajetórias e o modelo necessário existir, estime marks intermediários.

Use para:

* path drawdown;
* margin stress;
* early exit proxy;
* lifecycle feasibility.

Se não existir surface/model válido:

```text
pathwise_valuation_status = UNAVAILABLE
```

O payoff terminal ainda pode ser calculado.

## P6.S7.M04 — Greek engine

Use método adequado e publique:

```text
analytical
finite difference
surface derivative
scenario bump
unavailable
```

Valide estabilidade numérica.

## P6.S7.M05 — Break-even and shape engine

Calcule:

* break-even points;
* profit intervals;
* loss intervals;
* boundedness;
* convexity regions;
* monotonicity regions;
* discontinuities;
* tail slopes.

## P6.S7.M06 — Scenario evaluator

Avalie todos os candidatos nos cenários nominais da P5.

Produza:

* payoff;
* cost;
* path risk;
* scenario PnL;
* Greeks quando aplicável.

## P6.S7.M07 — Ambiguity evaluator

Avalie candidatos nas distribuições plausíveis alternativas.

Produza:

```text
worst_case_expected_payoff
worst_case_expected_utility
worst_case_CVaR
ambiguity_regret
distribution_sensitivity
```

Não otimize apenas a distribuição nominal.

---

# 18. P6.S8 — FEASIBILITY E DEFINED-RISK GATE

## P6.S8.M01 — Structural validator

Valide:

* legs não vazias;
* IDs únicos;
* contratos válidos;
* quantidades;
* sides;
* currencies;
* expirations;
* no zero-quantity;
* no exact cancelling legs;
* no malformed combination.

## P6.S8.M02 — Maximum-loss prover

O max loss deve ser:

* analiticamente provado;
* numericamente verificado em grid ampliada;
* testado em caudas;
* marcado com confidence.

Para múltiplos vencimentos, o cálculo pode exigir path assumptions.

Se não puder provar:

```text
DEFINED_RISK_NOT_PROVEN
```

## P6.S8.M03 — Margin feasibility gate

Aplique:

* exact margin quando disponível;
* defined-risk upper bound;
* conservative proxy;
* unavailable status.

## P6.S8.M04 — Liquidity gate

Considere:

* bid-ask;
* sizes;
* volume;
* open interest;
* staleness;
* leg count;
* weakest leg;
* combo quote availability.

Não agregue liquidez por média simples que esconda uma perna impossível.

## P6.S8.M05 — Cost gate

Considere:

* spread;
* commissions;
* fees;
* slippage proxy;
* legging risk proxy;
* borrow quando aplicável;
* exercise fee quando aplicável.

## P6.S8.M06 — Data quality gate

Bloqueie ou degrade por:

* repaired quote;
* stale quote;
* missing IV;
* missing liquidity;
* inconsistent surface;
* missing corporate-action information;
* unknown exercise style;
* unknown settlement.

## P6.S8.M07 — Economic sanity gate

Valide:

* payoff finito;
* no free positive payoff sem explicação;
* no negative cost arbitrage não auditado;
* realistic bounds;
* max gain/loss consistency;
* sign conventions;
* return-on-risk denominator.

---

# 19. P6.S9 — CANONICALIZATION E DEDUPLICAÇÃO

## P6.S9.M01 — Leg canonicalizer

1. Ordene pernas por chave canônica.
2. Agregue pernas idênticas.
3. Elimine quantidade zero.
4. Simplifique posições opostas.
5. Normalize sinais.
6. Preserve scale.

## P6.S9.M02 — Relative-scale normalizer

Estruturas:

```text
+1 call
-1 call
```

e:

```text
+2 calls
-2 calls
```

têm a mesma forma relativa, mas escala diferente.

Produza:

```text
shape_fingerprint
scale
```

Não apague a escala econômica.

## P6.S9.M03 — Payoff fingerprint builder

Avalie o payoff em grade normalizada contendo:

* cauda esquerda;
* região central;
* cauda direita;
* strikes;
* break-evens.

Hash do vetor normalizado.

## P6.S9.M04 — Economic fingerprint builder

Inclua:

```text
payoff shape
expirations
Greeks
cost
margin
liquidity
objective family
```

## P6.S9.M05 — Equivalence clustering

Agrupe:

* equivalentes exatos;
* equivalentes por escala;
* quase equivalentes por payoff;
* quase equivalentes por Greeks.

Não use apenas nomes de templates.

## P6.S9.M06 — Representative selector

Dentro de cluster de equivalência, preserve candidatos por critérios técnicos:

* menor custo;
* maior liquidez;
* menos pernas;
* menor repair magnitude;
* melhor data quality.

Isso não é ranking econômico geral.

---

# 20. P6.S10 — QUALITY-DIVERSITY ARCHIVE

## P6.S10.M01 — Descriptor registry

Descritores possíveis:

```text
entry_cost
maximum_loss
margin
leg_count
expiration_count
delta
gamma
vega
theta
payoff_asymmetry
profit_region_width
tail_protection
liquidity
target_payoff_error
```

Não use descritores excessivamente correlacionados sem diagnóstico.

## P6.S10.M02 — Archive grid or CVT builder

Modos:

```text
GRID_ARCHIVE
CVT_ARCHIVE
CLUSTER_ARCHIVE
```

A baseline pode usar grid simples e determinística.

## P6.S10.M03 — Niche quality evaluator

Qualidade local pode incluir:

```text
target payoff approximation
feasibility
data quality
cost efficiency
robustness
```

Não use score final da P7.

## P6.S10.M04 — Archive coverage reporter

Publique:

* nichos definidos;
* nichos preenchidos;
* coverage;
* candidatos por nicho;
* diversity;
* duplicates;
* empty regions;
* generation saturation.

## P6.S10.M05 — Publication budget selector

Selecione uma quantidade controlada de representantes por nicho.

Não publique milhões de candidatos.

Preserve:

* templates básicos;
* mutações;
* inverse-design solutions;
* robust alternatives;
* low-complexity alternatives.

---

# 21. P6 FINAL — PUBLICAÇÃO PARA P7

Independentemente da numeração final de subfases, publique:

```text
strategy_candidate_panel
strategy_leg_panel
strategy_market_snapshot
strategy_payoff_panel
strategy_scenario_evaluation_panel
strategy_ambiguity_evaluation_panel
strategy_greek_panel
strategy_risk_panel
strategy_cost_liquidity_panel
strategy_lineage_panel
strategy_generation_trace_panel
candidate_equivalence_panel
quality_diversity_archive
candidate_rejection_report
candidate_generation_audit
phase7_strategy_handoff_manifest
```

## Manifest

O manifest deve depender de:

```text
artifact IDs
content hashes
schema versions
record counts
decision time
cycle ID
snapshot hash
P5 belief hashes
P2 market hashes
generation policy version
solver versions
```

## Projection V1

Durante a migração, produza:

```text
candidate_feature_base_panel
candidate_universe_panel
option_instrument_feature_panel
contract_existence_report
option_feature_quality_report
candidate_generation_log
```

como views derivadas.

Nunca use V1 como modelo canônico interno.

---

# 22. THESIS INPUT PARA P7

A P6 deve publicar dados estruturados suficientes para a P7 construir uma thesis card.

Não gere narrativa livre como fonte de verdade.

Campos:

```text
objective_family
belief_state_ids
target_payoff_id
origin_template
mutation_trace
solver_origin
payoff_shape
profit_regions
failure_regions
scenario_dependencies
risk_dependencies
cost_dependencies
alternative_candidate_ids
equivalence_cluster
```

Um LLM poderá posteriormente redigir texto com base nesses campos, mas o texto não substitui dados.

---

# 23. MODOS OPERACIONAIS

## TEMPLATE_ONLY

Obrigatório para primeira baseline.

Inclui:

* contratos reais;
* templates;
* pricing;
* payoff;
* Greeks básicos;
* cenário;
* feasibility;
* dedup;
* publicação.

## TEMPLATE_MUTATION

Adiciona:

* deformações;
* assimetria;
* overlay;
* genealogia;
* complexity budget.

## INVERSE_DESIGN

Adiciona:

* target payoff;
* continuous relaxation;
* MILP;
* beam search;
* local search.

## QUALITY_DIVERSITY

Adiciona:

* archive;
* niches;
* coverage;
* diverse representatives.

## CHALLENGER

Permite:

* evolutionary search;
* learned proposer;
* generative candidate proposal.

Challenger nunca bloqueia `TEMPLATE_ONLY`.

---

# 24. ESTRATÉGIAS E POLÍTICAS INICIAIS

## Estratégias habilitadas na Release 1

```text
long underlying
short underlying, se suportado
long call
long put
debit vertical
defined-risk credit vertical
long straddle
long strangle
long butterfly
iron butterfly
long condor
iron condor
collar
risk reversal com risco definido
protected ratio
```

## Release 2

```text
calendar
diagonal
double calendar
broken-wing structures
quantity asymmetry
underlying overlay
```

## Release 3

```text
free-form inverse design
up to 4 legs
up to 2 expirations
small integer quantities
```

## Release 4

```text
up to 6 legs
advanced quality-diversity
cross-template synthesis
```

Não habilite toda complexidade no primeiro release.

---

# 25. AMERICAN OPTIONS, EXERCISE E ASSIGNMENT

A P6 deve registrar:

```text
exercise_style
settlement_type
dividend_state
early_exercise_model_status
assignment_model_status
```

Para opções americanas:

* payoff terminal sozinho pode não ser suficiente;
* calendar e diagonal exigem cuidado;
* short legs podem ser exercidas antecipadamente;
* dividendos podem alterar incentivos.

Política inicial possível:

```text
American multi-expiry structures:
DEGRADED ou BLOCKED
quando early-exercise risk não puder ser modelado.
```

Não trate opção americana como europeia silenciosamente.

---

# 26. VOLATILITY SURFACE E GREEKS

A P6 não deve construir uma superfície sofisticada escondida se a P5/P2 não a fornecem.

Defina uma porta:

```python
class OptionValuationPort:
    def price(...)
    def greeks(...)
    def mark_path(...)
```

Implementações:

```text
OBSERVED_QUOTE
ARBITRAGE_REPAIRED_SURFACE
BLACK_SCHOLES_PROXY
TREE_MODEL
UNAVAILABLE
```

Toda proxy deve ser identificada.

O preço observado domina para custo de entrada.

O modelo serve para:

* cenário;
* mark;
* Greeks;
* stress.

---

# 27. CUSTOS E EXECUÇÃO

A P6 estima, mas não executa.

Produza três camadas:

```text
quoted_cost
conservative_entry_cost
stress_entry_cost
```

Para multi-leg:

```text
atomic_combo_available
legging_required
legging_risk_proxy
weakest_leg_liquidity
```

P8 fará a simulação final.

---

# 28. COMPATIBILIDADE COM A P7 NOVA

A P7 deve receber candidatos completos.

Cada `candidate_id` precisa fechar em:

```text
candidate
legs
payoff
scenario evaluation
risk
cost/liquidity
Greeks
lineage
generation trace
manifest
```

A P7 não deve:

* reconstruir pernas;
* procurar contratos;
* inventar preço;
* recalcular max loss;
* consertar strategy identity.

Crie golden contract test:

```text
P6 output
→ P7 intake audit
→ exact candidate reconciliation
```

---

# 29. REASON CODES

Crie taxonomia consistente.

## Boundary

```text
P6_P5_MANIFEST_INVALID
P6_P5_FORECAST_FUTURE_DATED
P6_P5_SCENARIO_INVALID
P6_P2_MARKET_MANIFEST_INVALID
P6_MARKET_CLOCK_MISMATCH
```

## Contracts

```text
P6_CONTRACT_NOT_LISTED
P6_CONTRACT_EXPIRED
P6_CONTRACT_INVALID_AT_DECISION
P6_EXERCISE_STYLE_UNSUPPORTED
P6_SETTLEMENT_UNSUPPORTED
```

## Quotes

```text
P6_QUOTE_UNAVAILABLE
P6_QUOTE_STALE
P6_BID_ABOVE_ASK
P6_STATIC_ARBITRAGE_VIOLATION
P6_QUOTE_REPAIR_REQUIRED
```

## Generation

```text
P6_TEMPLATE_PRECONDITION_FAILED
P6_MUTATION_PRECONDITION_FAILED
P6_COMPLEXITY_BUDGET_EXCEEDED
P6_NO_FEASIBLE_CONTRACT_COMBINATION
P6_SOLVER_TIMEOUT
P6_SOLVER_INFEASIBLE
P6_SOLVER_NUMERICAL_FAILURE
```

## Risk

```text
P6_UNDEFINED_RISK
P6_MAXIMUM_LOSS_NOT_PROVEN
P6_MARGIN_UNAVAILABLE
P6_MARGIN_LIMIT_EXCEEDED
P6_COST_LIMIT_EXCEEDED
P6_LIQUIDITY_BELOW_MINIMUM
P6_PAYOFF_NON_FINITE
```

## Canonicalization

```text
P6_DUPLICATE_CANDIDATE
P6_EQUIVALENT_CANDIDATE
P6_REDUNDANT_LEG
P6_ZERO_QUANTITY_LEG
```

## Publication

```text
P6_LINEAGE_UNMAPPED
P6_MANIFEST_REFERENCE_INVALID
P6_INPUT_MUTATION_DETECTED
P6_OUTPUT_SCHEMA_INVALID
```

---

# 30. TESTES OBRIGATÓRIOS

## 30.1 Unitários

Todo módulo e serviço.

## 30.2 Golden integration

```text
P5 belief fixture
+
P2 option fixture
→ P6
→ P7 intake validation
```

## 30.3 Estratégias conhecidas

Verifique matematicamente:

* call;
* put;
* vertical;
* straddle;
* strangle;
* butterfly;
* iron condor;
* collar;
* protected ratio.

Compare payoff calculado com payoff analítico esperado.

## 30.4 Property-based tests

Use Hypothesis para:

* legs;
* strikes;
* quantities;
* expirations;
* payoffs;
* canonicalization;
* IDs;
* scenario mass;
* max loss;
* fingerprints;
* solver constraints.

## 30.5 Não arbitragem

Teste:

* vertical;
* butterfly;
* calendar;
* parity;
* intrinsic bounds;
* bad bid-ask;
* repair magnitude.

## 30.6 Temporal

Teste:

* future quote;
* future forecast;
* expired contract;
* listed-after-decision contract;
* future cache;
* future perturbation invariance.

## 30.7 Canonicalização

Teste que:

```text
mesmas legs em ordem diferente
→ mesmo candidate ID
```

Teste agregação e cancelamento.

## 30.8 Equivalência por escala

Teste:

```text
+1/-1
```

versus:

```text
+2/-2
```

mesma shape fingerprint, escalas diferentes.

## 30.9 Scenario evaluation

Teste:

* probabilities;
* nominal;
* ambiguity;
* tails;
* non-finite;
* stress;
* deterministic seed.

## 30.10 Solver

Teste:

* feasible;
* infeasible;
* timeout;
* optimal;
* non-optimal gap;
* determinism;
* constraint enforcement;
* no phantom contracts.

## 30.11 Adversarial

Inclua:

* candidate com contrato inexistente;
* short naked escondido;
* duplicate legs;
* max loss falso;
* margin zero inventada;
* liquidity ausente;
* extreme quantity;
* six-leg explosion;
* malformed mutation;
* solver solution outside universe;
* repaired quote sem flag;
* P5 density zero;
* belief-ratio explosion;
* ambiguity empty;
* unsupported American exercise;
* mixed currencies;
* mismatched multipliers.

## 30.12 Metamórficos

* permutar contracts não altera resultados;
* permutar scenarios não altera métricas;
* adicionar contrato não utilizado não altera candidato existente;
* adicionar dado futuro não altera passado;
* duplicar leg e dividir quantidade preserva payoff;
* escalar todas as quantities escala payoff e custo corretamente;
* remover candidato duplicado não altera archive coverage econômico.

## 30.13 Performance

Benchmarks separados:

```text
small chain
medium chain
large chain
```

Antes de rodar busca combinatória:

* estimate complexity;
* enforce timeout;
* cap memory;
* cap candidates;
* record pruning.

Nenhum teste pode travar indefinidamente.

---

# 31. CRITÉRIOS MATEMÁTICOS DE VALIDAÇÃO

Para cada candidato:

## Payoff reconciliation

[
\Pi_{\text{strategy}}(S)
========================

## \sum_i q_i \Pi_i(S)

\text{entry cost}
]

## Scenario expectation

[
E[\Pi]
======

\sum_s p_s \Pi_s
]

## Probability mass

[
\sum_s p_s = 1
]

dentro da tolerância.

## Expected Shortfall

Use convenção de perda positiva e documente o sinal.

## Maximum loss

Deve ser consistente entre:

* prova analítica;
* grid;
* tail extrapolation;
* scenario stress.

## Cost

[
C_{\text{strategy}}
===================

\sum_i C_i
+
\text{fees}
+
\text{slippage proxy}
]

## Target approximation

[
\text{error}
============

\sum_s w_s
\left(
\Pi_{\text{candidate},s}
------------------------

g^*_s
\right)^2
]

Inclua versões:

* nominal;
* weighted;
* tail-weighted;
* ambiguity worst-case.

---

# 32. QUALITY-DIVERSITY NÃO É RANKING

Documente explicitamente:

```text
A P6 preserva diversidade de candidatos.
A P7 determina preferência.
```

O archive pode dizer:

```text
“melhor representante encontrado para este nicho técnico”
```

Não pode dizer:

```text
“melhor trade geral”
```

---

# 33. GOVERNANÇA DOS SOLVERS

Defina interface única:

```python
class StrategySolverPort:
    def solve(problem: StrategySynthesisProblem) -> SolverResult:
        ...
```

`SolverResult`:

```text
status
candidate_set
objective_values
best_bound
gap
runtime
iterations
seed
diagnostics
```

Nenhum solver escreve diretamente no artifact store oficial.

O orchestrator valida e canonicaliza primeiro.

---

# 34. QUALIDADE DE CÓDIGO

Metas:

```text
máximo de 350 linhas por arquivo
máximo de 60 linhas por função
máximo de 180 linhas por classe
```

Exceções justificadas.

Exija:

```text
Ruff
mypy strict
pytest
Hypothesis
coverage
```

Matriz:

```text
Python 3.11
Python 3.12
Python 3.13
Python 3.14
```

Proibido:

* `Any` generalizado;
* imports circulares;
* estado global;
* paths absolutos;
* network em testes;
* segredo em config;
* broad exception convertendo erro em sucesso;
* `except Exception: pass`;
* NaN/Infinity em JSON;
* default econômico;
* código legado morto;
* múltiplas taxonomias de erro;
* múltiplos domain models.

---

# 35. SEGURANÇA E INTEGRIDADE

* paths devem permanecer dentro do workspace;
* writes atômicos;
* no overwrite com bytes diferentes;
* exact-byte SHA-256;
* post-write verification;
* locking quando necessário;
* serialization determinística;
* IDs sem colisão;
* logs sem payload sensível;
* no arbitrary code execution em configs;
* safe parser para DSL;
* solver inputs limitados;
* timeout externo;
* subprocess isolation quando necessário.

---

# 36. OBSERVABILIDADE

Cada módulo emite:

```text
module_id
run_id
cycle_id
status
reason_code
input_artifact_ids
output_artifact_ids
input_hashes
output_hashes
duration
memory
candidate_count_in
candidate_count_out
rejection_count
dedup_count
solver_stats
warnings
seed
policy_version
```

---

# 37. MODOS DE RELEASE

## Release A — Candidate Foundation

Fechar:

* snapshot;
* domain;
* templates;
* payoff;
* cost;
* Greeks básicos;
* feasibility;
* canonicalization;
* P7 handoff.

## Release B — Mutation

Adicionar:

* deformation;
* asymmetric quantities;
* overlay;
* equivalence;
* diversity.

## Release C — Inverse Design

Adicionar:

* target payoff;
* continuous solver;
* MILP;
* beam;
* local search.

## Release D — Robust and QD

Adicionar:

* ambiguity evaluation;
* quality-diversity;
* evolutionary challenger.

## Release E — Advanced Instrument Lifecycle Readiness

Adicionar suporte mais profundo a:

* American exercise;
* calendars;
* diagonals;
* assignment-risk inputs;
* richer margin methods.

Não misture gestão dinâmica de posição; isso pertence à P8.

---

# 38. OWNERSHIP DE AGENTES

Caso use agentes paralelos:

```text
AG-0 — Architecture Guardian / Integrator
AG-1 — P5/P2 Boundary and PIT Snapshot
AG-2 — Canonical Domain, Grammar and Identity
AG-3 — Template Generation
AG-4 — Mutation and Canonicalization
AG-5 — Target Payoff and Market-Implied State
AG-6 — Solvers and Inverse Design
AG-7 — Pricing, Greeks and Scenario Evaluation
AG-8 — Feasibility, Costs, Margin and Liquidity
AG-9 — Quality-Diversity and Publication
AG-10 — Independent Adversarial Auditor
```

Cada agente:

* branch separada;
* worktree separado;
* ownership explícito;
* não edita contracts congelados sem Architecture Change Request;
* não cria abstração compartilhada sem pesquisa prévia;
* não modifica outras fases.

Somente AG-0 integra.

---

# 39. DELIVERABLES

Entregue um único ZIP final contendo:

```text
src/
tests/
contracts/
schemas/
configs/
fixtures/
qualification/
reports/
tools/
README.md
ARCHITECTURE.md
PHASE_FUNCTION.md
SUBPHASES.md
MODULE_CATALOG.md
MODULE_REGISTRY.yaml
CONTRACT_REGISTRY.yaml
STRATEGY_TEMPLATE_REGISTRY.yaml
MUTATION_OPERATOR_REGISTRY.yaml
OBJECTIVE_FAMILY_REGISTRY.yaml
CONSTRAINT_POLICY_REGISTRY.yaml
SOLVER_REGISTRY.yaml
P5_P6_COMPATIBILITY_MATRIX.md
P6_P7_COMPATIBILITY_MATRIX.md
P6_SUBPHASE_ARCHITECTURE_DECISION.md
STRATEGY_DOMAIN_SPEC.md
TARGET_PAYOFF_SPEC.md
SOLVER_SPEC.md
PAYOFF_VALIDATION_REPORT.md
STATIC_ARBITRAGE_REPORT.md
SCENARIO_EVALUATION_REPORT.md
QUALITY_DIVERSITY_REPORT.md
ADVERSARIAL_TEST_REPORT.md
PERFORMANCE_REPORT.md
MIGRATION_V1_TO_V2.md
LITERATURE_MAPPING.md
RISK_REGISTER.md
CHANGELOG.md
TEST_REPORT.md
COVERAGE_REPORT.md
RELEASE.json
SBOM.cdx.json
FILE_MANIFEST.json
PACKAGE_MANIFEST.json
SHA256SUMS
```

Também entregue:

* inventário de arquivos modificados;
* módulos preservados;
* módulos reescritos;
* módulos novos;
* módulos removidos;
* contratos novos;
* contratos depreciados;
* schemas;
* dívida restante;
* capacidades opcionais;
* comandos;
* resultados;
* ZIP e hash final.

---

# 40. LITERATURE MAPPING

Crie `LITERATURE_MAPPING.md`.

Mapeie cada técnica para:

```text
conceito
referência
módulo P6
o que foi realmente implementado
o que não foi implementado
hipóteses
limitações
testes
```

Inclua ao menos:

* state-contingent claims e densidades implícitas;
* static replication;
* arbitrage-free option prices;
* portfolio optimization with options;
* robust cost-efficient payoffs;
* sparse/cardinality-constrained optimization;
* mixed-integer optimization;
* multiobjective optimization;
* quality-diversity;
* model ambiguity;
* deep hedging apenas como fronteira futura com P8.

Não use paper como decoração.

---

# 41. DEFINITION OF DONE

A P6 não está concluída apenas porque testes unitários passam.

## Software closure

* módulos oficiais executados;
* contracts válidos;
* schemas fortes;
* runtime validation;
* sem placeholders;
* sem outputs órfãos;
* deterministic replay;
* clean extraction;
* manifestos corretos.

## Temporal closure

* nenhum dado futuro;
* contratos válidos na decisão;
* forecasts anteriores à decisão;
* future perturbation invariance;
* cache cutoff seguro.

## Market closure

* contracts reais;
* quotes reais;
* bid/ask;
* calendars;
* static arbitrage diagnostics;
* no phantom instrument.

## Strategy closure

* legs canônicas;
* templates;
* payoff reconciliado;
* risco definido;
* custos;
* liquidez;
* Greeks;
* dedup;
* identity;
* lineage.

## Scenario closure

* cenários P5 consumidos;
* probabilidades;
* ambiguity;
* stress;
* expected payoff;
* ES;
* max loss;
* path risk quando disponível.

## Solver closure

* constraints respeitadas;
* timeout;
* infeasible status;
* determinism;
* solver diagnostics;
* no out-of-universe instruments.

## Compatibility closure

* P5 V2 nativa;
* P5 V1 adapter explícito;
* P7 V2 handoff;
* P7 V1 projection temporária;
* hashes e receipts.

## Scientific closure

* templates como baseline;
* solver comparison;
* ablation;
* approximation error;
* robustness;
* diversity;
* computational budget.

## Production closure

Mantenha:

```text
production_promotion_allowed = false
```

até existir:

* chain real qualificada;
* pricing validado;
* margin rules;
* execution calibration;
* live monitoring;
* incident recovery;
* aprovação independente.

---

# 42. CRITÉRIO FINAL DE QUALIDADE

O resultado deve ser:

```text
robusto
legível
modular
teoricamente fundamentado
economicamente correto
temporalmente seguro
testável
auditável
determinístico
extensível
compatível
fail-closed
```

O resultado não deve ser:

```text
enumerador combinatório ingênuo
coleção de nomes de estratégias
motor com contratos fictícios
P7 escondida dentro da P6
P8 escondida dentro da P6
otimizador sem constraints
solver que afirma ótimo sem prova
payoff sem custo
risco sem margem
score disfarçado de quality
pipeline dependente de GPU
arquitetura Frankenstein
```

---

# 43. FORMATO DO RELATÓRIO FINAL

Reporte exatamente:

```text
BASELINE:
BASELINE_SHA256_EXPECTED:
BASELINE_SHA256_ACTUAL:
TARGET_RELEASE:
SUBPHASE_ARCHITECTURE_DECISION:
FILES_CHANGED:
MODULES_PRESERVED:
MODULES_REWRITTEN:
MODULES_ADDED:
MODULES_REMOVED:
CONTRACTS_ADDED:
CONTRACTS_CHANGED:
SCHEMAS_ADDED:
STRATEGY_TEMPLATES_IMPLEMENTED:
MUTATION_OPERATORS_IMPLEMENTED:
SOLVERS_IMPLEMENTED:
OPERATIONAL_MODES:
TESTS_PASSED:
BRANCH_COVERAGE:
TYPE_CHECK:
LINT:
PROPERTY_TESTS:
DETERMINISTIC_REPLAY:
STATIC_ARBITRAGE_QUALIFICATION:
PAYOFF_RECONCILIATION:
SCENARIO_QUALIFICATION:
DEFINED_RISK_QUALIFICATION:
SOLVER_QUALIFICATION:
QUALITY_DIVERSITY_QUALIFICATION:
P5_COMPATIBILITY:
P7_COMPATIBILITY:
TEMPORAL_QUALIFICATION:
KNOWN_LIMITATIONS:
PRODUCTION_PROMOTION_ALLOWED:
FINAL_STATUS:
OUTPUT_ZIP:
OUTPUT_SHA256:
```

Valores permitidos para `FINAL_STATUS`:

```text
PASS
PASS_WITH_NON_BLOCKING_DEBT
FAIL_BASELINE_INTEGRITY
FAIL_CONTRACT
FAIL_TEMPORAL
FAIL_MARKET_DATA
FAIL_STATIC_ARBITRAGE
FAIL_PAYOFF
FAIL_DEFINED_RISK
FAIL_SCENARIO
FAIL_SOLVER
FAIL_COMPATIBILITY
FAIL_RELEASE_INTEGRITY
```

Nunca marque `PASS` por conveniência.

Não esconda capabilities ausentes.

Não transforme uma fixture em evidência econômica.

Uma falha explícita e rastreável é preferível a uma estrutura fictícia aparentemente funcional.
