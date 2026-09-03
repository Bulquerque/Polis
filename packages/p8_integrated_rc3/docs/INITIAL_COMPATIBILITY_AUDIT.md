# P8 vNext — Auditoria de Compatibilidade e Plano de União dos Cinco Agentes

**Data da auditoria:** 2026-08-04  
**Escopo:** P8.S1–P8.S10, 58 módulos, cinco entregas de agentes  
**Objetivo:** determinar se as entregas podem ser reunidas, identificar incompatibilidades e definir um processo seguro de consolidação.

---

## 1. Veredito executivo

As cinco entregas formam uma base tecnicamente promissora, mas **não podem ser simplesmente copiadas ou instaladas lado a lado e declaradas uma P8 integrada**.

```text
COMPATIBILIDADE FÍSICA DO SOURCE:        ALTA
COMPATIBILIDADE DE DEPENDÊNCIAS:         ALTA, APÓS UNIFICAÇÃO
COMPATIBILIDADE DE NAMESPACE:            MÉDIA, EXIGE ÁRVORE ÚNICA
COMPATIBILIDADE DE CONTRATOS INTERNOS:   BAIXA
COMPATIBILIDADE ECONÔMICA ENTRE AGENTES: BLOQUEADA
QUALIDADE LOCAL DAS ENTREGAS:            BOA A MUITO BOA
PRONTIDÃO PARA MERGE DIRETO:              NÃO
PRONTIDÃO PARA INTEGRAÇÃO CONTROLADA:     SIM
```

A forma correta de unir é:

```text
cinco entregas de agentes
→ uma árvore física de source
→ um foundation/contracts kernel canônico
→ adapters temporários e estritos nas fronteiras
→ contratos econômicos V1 fechados
→ testes producer/consumer com bytes reais
→ golden threads ponta a ponta
→ uma única wheel e um único ZIP P8
```

Não é recomendado entregar cinco wheels independentes como produto final.

---

## 2. Entradas auditadas

### Agente 1 — P8.S1/S2

```text
Arquivo: P8_AGENT1_S1_S2_INTEGRATED_V1(1).zip
SHA-256: 79ab633e3f8a3ea42937f73f877a1b48aefc536fe41de7688a16f8593fa4f02e
Subfases: S1 e S2
Módulos: 12
Testes reexecutados:
  S1: 85 PASS
  S2: 63 PASS
  Integração interna: 13 PASS
  Total: 161 PASS
```

### Agente 2 — P8.S3/S4

```text
Arquivo: P8_AGENT_2_S3_S4_INTEGRATED_V1(1).zip
SHA-256: c0335526db36695d1affb77987d8240f3a2b5cd091fb24e86be65933c23764d3
Subfases: S3 e S4
Módulos: 12
Testes reexecutados: 122 PASS
```

### Agente 3 — P8.S5/S6

```text
Arquivo: P8_AGENT_3_INTEGRATED_S5_S6_V1_FINAL(1).zip
SHA-256: bbb9d41fccff396dcd708ac443ff7129f3353b1fbbc7dad2dc668283ed6003d8
Subfases: S5 e S6
Módulos: 12
Testes presentes na árvore integrada e reexecutados: 14 PASS
```

A documentação do Agente 3 registra regressões adicionais dos componentes, mas essas suítes não estão materializadas integralmente como testes executáveis na árvore integrada. A release final deve incorporar esses testes, não apenas seus logs.

### Agente 4 — P8.S7/S8

```text
Arquivo: P8_AGENT_4_COMPLETE_CONSOLIDATED_V1_2_0(1).zip
SHA-256: 16e99029d9ba282ba874e85fecccb6cc059f0203d61c89466ee44217cdab8b11
Subfases: S7 e S8
Módulos: 13
Testes reexecutados: 99 PASS
```

### Agente 5 — P8.S9/S10

A entrega foi localizada pelos arquivos indexados do projeto:

```text
Pacote: P8_AGENT5_S9_S10_UNIFIED_V1
Versão: 0.1.0
Subfases: S9 e S10
Módulos: 9
Testes declarados: 194 PASS
Schemas: 24
ZIP SHA-256 declarado:
ffd392256ee8032263dc4617a6b822cfc8aa43d8151b4101447a9f0f0235a61a
Wheel SHA-256 declarado:
fccc380d7a81c81bf8b827c61b5944b14219acfd9ead8eb06982c8eb79dbb4fc
Reprodutibilidade declarada: PASS
Produção: bloqueada
```

**Limitação da presente auditoria:** o ZIP do Agente 5 não apareceu montado no filesystem ativo de `/mnt/data`. Assim, sua arquitetura, contratos e evidências foram analisados pelos arquivos indexados e pelos relatórios de build, mas seus bytes não foram reextraídos nem seus 194 testes reexecutados nesta sessão.

---

## 3. Compatibilidade física do código

### 3.1 Colisões de caminhos

Os sources dos Agentes 1–4 foram copiados para uma árvore de prova única. Não foram encontradas colisões de caminho relativo entre seus arquivos produtivos.

```text
Arquivos source relativos analisados: 278
Colisões exatas de path: 0
```

Isso indica que a divisão por subfases funcionou razoavelmente bem como ownership.

### 3.2 Importação em uma única árvore

Na árvore física unificada, os imports das oito primeiras subfases passaram:

```text
PASS S1
PASS S2
PASS S3
PASS S4
PASS S5
PASS S6
PASS S7
PASS S8
```

Portanto, **é possível montar uma única package tree**.

### 3.3 Problema do `__init__.py` do Agente 4

O Agente 4 adiciona:

```python
from .api import run_s7, run_s8
from .version import __version__
```

em:

```text
quant_pipeline/phase_08_portfolio_control/__init__.py
```

Os Agentes 1–3 tratam a mesma árvore como namespace distribuído. Quando vários `src` independentes entram no `PYTHONPATH`, o package regular do Agente 4 pode ocultar as demais porções.

### Decisão

A release final deve ter:

```text
UMA árvore física
UMA wheel
UM __init__.py canônico ou namespace sem root init
UMA api.py canônica
```

O `__init__.py` atual do Agente 4 não deve ser copiado sem alteração. Ele deve ser reescrito como superfície pública da fase inteira.

### 3.4 Layout inconsistente

Os agentes usam layouts diferentes:

```text
A1: s01_boundary / s02_candidate_context
A2: scenario_engineering / risk_state
A3: s05_optimization / s06_risk_lifecycle
A4: subphases/s07_execution / subphases/s08_stateful_engine
A5: subphases/s09_runtime_assurance / subphases/s10_audit_release
```

### Layout canônico recomendado

```text
src/quant_pipeline/phase_08_portfolio_control/
  api.py
  version.py
  foundation/
  contracts/
  ports/
  adapters/
  orchestration/
  subphases/
    s01_boundary/
    s02_candidate_context/
    s03_scenario_engineering/
    s04_joint_risk_state/
    s05_optimization/
    s06_risk_lifecycle/
    s07_execution/
    s08_stateful_engine/
    s09_runtime_assurance/
    s10_audit_release/
```

Os caminhos antigos podem permanecer durante uma release como reexports de compatibilidade, com remoção planejada.

---

## 4. Dependências e ambiente unificado

### Restrições atuais

| Entrega | Python | Pydantic | NumPy | SciPy | JSON Schema |
|---|---|---|---|---|---|
| A1 | `>=3.13,<3.15` | `>=2.13,<3` | — | — | `>=4.26,<5` |
| A2 | `>=3.11` | `>=2.8,<3` | `>=2,<3` | `>=1.12,<2` | `>=4.20,<5` |
| A3 | `>=3.11` | `>=2.11,<3` | `>=2,<3` | `>=1.14,<2` | `>=4.23,<5` |
| A4 | `>=3.11` | `>=2.12,<3` | — | — | — |
| A5 padrão | `>=3.13,<3.15` | `>=2.12,<3` | opcional | opcional | `>=4.25,<5` |

### Lock recomendado para a primeira release integrada

```toml
requires-python = ">=3.13,<3.15"

dependencies = [
  "pydantic>=2.13,<3",
  "PyYAML>=6,<7",
  "jsonschema>=4.26,<5",
  "numpy>=2,<3",
  "scipy>=1.14,<2",
]
```

Esse lock é compatível com os quatro ZIPs reexecutados e com o padrão declarado pelo Agente 5.

### Observação

A futura ampliação para Python 3.11/3.12 deve ser uma qualificação separada. Não deve ser prometida nesta primeira união porque o Agente 1 congelou 3.13+.

---

## 5. Higiene dos ZIPs

### Inventário direto dos arquivos compactados

| Entrega | Entradas | `.pyc` | `__pycache__` | `.egg-info` | `.pytest_cache` | `.coverage` |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 531 | 0 | 0 | 18 | 0 | 0 |
| A2 | 267 | 0 | 0 | 0 | 0 | 0 |
| A3 | 351 | 75 | 75 | 5 | 5 | 1 |
| A4 | 199 | 0 | 0 | 0 | 0 | 0 |

### Bloqueios

- O Agente 1 inclui metadata `.egg-info` dentro dos sources.
- O Agente 3 inclui bytecode, caches de pytest, `.coverage` e `.egg-info`.
- O manifesto do Agente 3 inclui arquivos mutáveis de bytecode; executar os testes pode alterar seus hashes.

### Regra da release final

Excluir integralmente:

```text
__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/
.coverage
coverage.json/htmlcov
build/
```

Depois da limpeza, gerar do zero:

```text
source manifest
artifact manifest
wheel manifest
SBOM
SHA-256
```

---

## 6. Matriz de compatibilidade entre os agentes

| Fronteira | Estado | Diagnóstico |
|---|---|---|
| A1 → A2 | **VERMELHO** | O bundle A1 existe, mas A2 não o consome; A2 recebe um request independente |
| A2 → A3 | **VERMELHO** | Dois modelos chamados DecisionReadyRiskBundle têm estruturas incompatíveis |
| A3 → A4 | **VERMELHO** | A3 autoriza ações por candidato; A4 exige targets físicos por instrumento |
| A4 → A5 | **AMARELO/VERMELHO** | Conceito alinhado, mas o bundle A4 é mais estreito que o contrato exigido por A5 |
| A5 → A4 | **VERMELHO** | Comando runtime A4 é fraco demais para o supervisor A5 |
| A5 → P9 | **AMARELO** | Schema/model consumer declarado; consumidor P9 vNext real não foi provado |
| A5 → P0 | **AMARELO** | Handoff técnico gerado, autorização continua externa e bloqueada |
| Coexistência source | **VERDE** | Funciona em uma única árvore física |
| Dependências | **VERDE** | Interseção clara em Python 3.13 e Pydantic 2.13 |

---

# 7. Fronteira Agente 1 → Agente 2

## O que o Agente 1 publica

`P8CandidateContextBundleV1` contém os objetos inline:

```text
snapshot_id / snapshot_hash
normalized_intents
exposure_graph
equivalence_groups
soft_similarity_requests
netting_transform
static_action_universe
ordinal_preferences
content_sha256
```

## O que o Agente 2 realmente consome

A API S3 do Agente 2 recebe uma estrutura própria com:

```text
BeliefRecord
strategy families
historical samples
realized samples
scenario policies
```

Ela não recebe `P8CandidateContextBundleV1`.

## Consequência

Não existe conexão executável A1→A2. As duas partes foram testadas isoladamente com fixtures próprias.

## Correção recomendada

Criar um consumidor estrito:

```text
A1CandidateContextConsumerV1
```

Responsabilidades:

1. validar hash e snapshot;
2. resolver as referências P5/P6 preservadas pela S1;
3. extrair candidatos admitidos e suas unit economics;
4. construir o request canônico da S3;
5. preservar ordinal preferences sem transformá-las em probabilidades;
6. publicar consumer receipt.

### Melhor mudança estrutural

Ampliar o bundle A1 com referências obrigatórias:

```text
candidate_terminal_state_ledger_ref
resolved_p5_belief_refs
resolved_p6_economic_package_refs
unit_economic_exposure_ref
conservation_proof_ref
```

Sem isso, o Agente 2 precisa buscar informação por caminhos paralelos.

---

# 8. Fronteira Agente 2 → Agente 3

## Saída real do Agente 2

`P8DecisionReadyRiskBundle` é um bundle fino de referências:

```text
bundle_id
run_id
cycle_id
decision_time
s3_result_sha256
pnl_cube_ref
dependence_state_ref
greek_path_state_ref
liquidity_state_ref
margin_funding_state_ref
candidate_sizability
risk_capability_receipt
content_sha256
```

## Entrada real do Agente 3

O `DecisionReadyRiskBundle` do Agente 3 usa:

```text
ArtifactEnvelope
DecisionReadyRiskPayload
```

O payload espera informação já materializada e economicamente pronta:

- candidates;
- cenário e probabilidades;
- risk limits por horizonte;
- policy context;
- ambiguity;
- mandatory stresses;
- ordinal preferences;
- MPC horizon.

## Consequência

Os tipos possuem nomes semelhantes, mas não representam o mesmo contrato.

```text
A2 bundle = índice de artefatos e sizability
A3 bundle = problema completo de decisão
```

O Agente 3 registra que sua integração não utilizou bytes reais do Agente 2. Assim, os 14 testes integrados não provam esta fronteira.

## Contrato canônico recomendado

```text
P8_DECISION_READY_RISK_BUNDLE_V1
```

### Envelope

```text
artifact_id
contract_version
schema_version
producer_release
run_id
cycle_id
decision_time
market_cutoff_at
computed_at
available_at
canonicalization_version
payload_sha256
lineage
```

### Payload

```text
decision_snapshot_ref
action_universe_ref
candidate_specifications
candidate_sizability
scenario_set_ref
scenario_probability_semantics
mandatory_stress_refs
pnl_cube_ref
dependence_ref
greek_path_ref
liquidity_ref
margin_funding_ref
ambiguity_actionability
risk_limits
ordinal_preference_constraints
mpc_policy_context
component_receipts
```

### Política de tamanho

- Arrays grandes ficam como referências content-addressed.
- Informações pequenas necessárias ao solver ficam inline.
- O consumer resolve as referências uma única vez e sela um `OptimizationProblemInput` interno.

---

# 9. Fronteira Agente 3 → Agente 4

## Saída real do Agente 3

O `ExecutionAuthorizationBundle` do Agente 3 possui:

```text
risk_gate
hedge_plan
lifecycle_plan
emergency_plan
authorized_actions
valid_from / valid_until
execution_authority
```

As ações autorizadas são centradas no `candidate_id` e na quantidade do candidato.

## Entrada real do Agente 4

O `P8ExecutionAuthorizationBundle` do Agente 4 exige:

```text
um target físico líquido por instrumento
instrument specs
authorization por target
current physical positions
current virtual positions
open-order exposures
virtual allocations que fecham exatamente
refs de dual book, risk, hedge e lifecycle
```

## Consequência

Há uma mudança econômica ainda não implementada:

```text
quantidade por candidato
→ expansão por pernas P6
→ netting físico
→ target por instrumento
→ atribuição virtual
```

Isso não pode ser um adapter superficial no Agente 4. É a finalização da decisão de portfólio e pertence à fronteira S6.

## Correção recomendada

Renomear a saída atual do Agente 3 para:

```text
P8_RISK_AUTHORIZATION_DECISION_V1
```

Depois, implementar no final da S6:

```text
execution_target_materializer
```

que consome:

- candidate quantities;
- P6 unit leg definitions;
- dual-book/netting map;
- current positions;
- open orders;
- instrument registry;
- risk/lifecycle authorizations.

E publica exatamente o contrato rico do Agente 4:

```text
P8_EXECUTION_AUTHORIZATION_BUNDLE_V1
```

## Invariantes

```text
virtual allocations sum = physical target
one net physical target per instrument
current virtual positions reconcile to physical positions
open-order virtual allocations reconcile by instrument
no quantity changes after risk receipt without reauthorization
```

---

# 10. Fronteira Agente 4 → Agente 5

## Saída atual do Agente 4

`StatefulEvidenceBundle` contém:

```text
status
execution_state
positions
accounting
valuation
management
checkpoint
replay_manifest
content_sha256
```

## Entrada planejada do Agente 5

O Agente 5 exige um `P8_STATEFUL_EVIDENCE_BUNDLE_V1` com:

- ordered event queue reference;
- order/fill ledgers;
- physical e virtual positions;
- intent-to-physical allocation;
- lifecycle/settlement;
- cash, premium, cost, margin, collateral;
- valuation, NAV, PnL, drawdown;
- management actions;
- checkpoints/replay;
- mark quality;
- open orders;
- pending settlements;
- upstream bundle references;
- consumer receipts.

## Diagnóstico

Grande parte da informação existe nos subobjetos do Agente 4, mas faltam no envelope atual:

```text
contract/schema versions
producer release
run/cycle/decision clocks
prior bundle references
consumer receipts
mark-quality authority explícita
open-order/pending-settlement summary explícito
P4→P8 lineage closure
```

## Correção recomendada

Manter o `StatefulEvidenceBundle` como estado interno da S8 e envolvê-lo em:

```text
P8_STATEFUL_EVIDENCE_BUNDLE_V1
```

com:

```text
IntegrityEnvelope
stateful_evidence_ref
A1_bundle_ref
A2_bundle_ref
A3_bundle_ref
consumer_receipts
candidate/order/fill/position conservation receipt
runtime baseline
mark-quality summary
open obligations summary
```

Esse bundle deve ser o único input autoritativo da S9/S10.

---

# 11. Fronteira Agente 5 → Agente 4

## Comando atual do Agente 4

```text
command_id
event_time
mode
reason_code
```

## O que o Agente 5 precisa emitir

O supervisor da S9 produz decisões de segurança que precisam ser:

- vinculadas ao estado exato;
- temporalmente válidas;
- idempotentes;
- justificadas por alertas/violations;
- acompanhadas de feasibility proof;
- restritas a transições permitidas.

## Contrato canônico recomendado

```text
P8_RUNTIME_CONTROL_COMMAND_V1
```

Campos mínimos:

```text
command_id
contract_version
schema_version
producer_module
run_id
cycle_id
event_time
available_at
valid_until
source_state_hash
command_sequence
idempotency_key
mode
reason_codes
alert_refs
violation_refs
fallback_plan_ref
feasibility_proof_ref
affected_order_ids
affected_instrument_ids
affected_candidate_ids
content_sha256
```

## Invariantes

- o comando refere-se ao state hash corrente;
- não está expirado;
- não repete sequence/idempotency;
- não aumenta risco;
- a transição de modo é permitida;
- `HALT` não é aplicado cegamente quando existe partial fill;
- o Agente 5 nunca possui um broker/send-order port.

O Agente 4 aplica o comando como evento pela mesma máquina de estados usada no backtest/live.

---

# 12. Reotimização

O Agente 4 já possui `ReoptimizationRequest`, mas o contrato precisa ser ampliado.

## Contrato recomendado

```text
P8_REOPTIMIZATION_REQUEST_V1
```

Campos adicionais:

```text
run_id
source_decision_time
request_available_at
trigger_event_refs
current_state_ref
current_state_hash
invalidated_target_ref
requested_snapshot_semantics
urgency
idempotency_key
```

O request não chama a S5 diretamente.

```text
S8/S9 publica request
→ orquestrador fecha o ciclo atual
→ S1 cria novo snapshot
→ S3/S4 atualizam riscos
→ S5 reotimiza
```

---

## 13. Kernel compartilhado — maior dívida transversal

Cada agente criou versões próprias de:

- `StrictModel`;
- hashing;
- artifact references;
- envelopes;
- clocks;
- enums;
- errors;
- status e receipts.

Manter todas criaria cinco autoridades concorrentes.

## Foundation canônico

```text
foundation/
  identity.py
  time.py
  horizons.py
  money.py
  units.py
  integrity.py
  serialization.py
  events.py
  errors.py
  reason_codes.py
  terminal_states.py
  receipts.py
```

## Contracts canônicos

```text
contracts/
  external/
  cross_subphase/
  artifacts/
  policies/
  runtime/
  release/
```

## Regra de hash

Não incluir o próprio hash no preimage.

```text
canonical_payload
→ canonical serialization
→ payload_sha256
→ IntegrityEnvelope(payload, payload_sha256)
```

Congelar:

```text
UTF-8
UTC Z
JSON key order
array order
Decimal representation
float non-finite forbidden
null policy
timezone policy
canonicalization_version
```

## Estratégia de migração

1. criar o foundation canônico;
2. testar paridade com cada helper antigo;
3. migrar um agente de cada vez;
4. manter reexports temporários;
5. remover implementações duplicadas antes da release final.

---

## 14. Registries, IDs e versões

### Situação

As entregas usam versões independentes e estruturas diferentes de registry.

### Release integrada

```text
Package: quant-pipeline-p8
Version: 0.1.0rc1  # nova versão; não reutilizar versão de agente
```

Contratos possuem versões independentes:

```text
P8_CANDIDATE_CONTEXT_BUNDLE_V1: 1.0.0
P8_DECISION_READY_RISK_BUNDLE_V1: 1.0.0
P8_EXECUTION_AUTHORIZATION_BUNDLE_V1: 1.0.0
P8_STATEFUL_EVIDENCE_BUNDLE_V1: 1.0.0
P8_RUNTIME_CONTROL_COMMAND_V1: 1.0.0
```

## Um único registry gerador

A fonte deve gerar:

```text
module registry
contract registry
schema registry
reason-code registry
capability registry
policy registry
IO matrix
documentation tables
```

## Módulos S6

Cada arquivo operacional precisa declarar um `MODULE_ID` canônico e coincidir com o registry. Não basta o ID aparecer apenas em receipts do finalizer.

---

## 15. Estratégia de testes unificada

### Problema de discovery

Ao juntar todos os testes do Agente 1, nomes repetidos como `test_package_surface.py` podem colidir. Alguns testes também importam `factories` como módulo top-level.

## Layout recomendado

```text
tests/
  __init__.py
  s01_boundary/
  s02_candidate_context/
  s03_scenario_engineering/
  s04_joint_risk_state/
  s05_optimization/
  s06_risk_lifecycle/
  s07_execution/
  s08_stateful_engine/
  s09_runtime_assurance/
  s10_audit_release/
  contracts/
  integration/
  golden/
  release/
```

Configurar:

```toml
addopts = "--import-mode=importlib --strict-markers --strict-config"
```

E usar imports relativos ou package-qualified.

## Testes locais atualmente comprovados

```text
Agente 1: 161
Agente 2: 122
Agente 3: 14 na árvore integrada
Agente 4: 99
Agente 5: 194 declarados
```

Total observável/declarado:

```text
590 testes
```

Esse total não é ainda uma suíte de integração, porque quase todos são testes locais.

## Pairwise consumer tests obrigatórios

```text
A1 producer → A2 real consumer
A2 producer → A3 real consumer
A3 producer → A4 real consumer
A4 producer → A5 real consumer
A5 runtime producer → A4 real consumer
A5 P9 handoff → P9 vNext real consumer
A5 release handoff → P0 real consumer
```

Mocks permissivos não fecham esses gates.

---

## 16. Golden threads obrigatórios

### GT-01 — NO_ACTION_VALID

```text
P7 all-abstained
→ S1/S2 conservam candidatos
→ S3/S4 não fabricam cenários/risco
→ S5 no target
→ S7 no orders
→ S8 preserva estado
→ S9 sem intervenção artificial
→ S10/P9 evidence completo
```

### GT-02 — RANKED_LINEAR_EXECUTED

```text
candidato linear válido
→ cenários
→ risco
→ sizing
→ target físico
→ order/fill
→ accounting
→ replay
→ auditoria
```

### GT-03 — MULTI_LEG_OPTION

```text
candidate shape P6
→ candidate quantity
→ leg expansion/netting
→ combo/legging
→ lifecycle
→ settlement
→ dual-book attribution
```

### GT-04 — PARTIAL_FILL_SAFE

```text
fill parcial
→ temporary exposure
→ runtime alert
→ safety command
→ hedge/unwind
→ estado e accounting consistentes
```

### GT-05 — MARGIN_SHOCK

```text
margin increase
→ live violation
→ no-new-risk/risk reduction
→ liquidation plan
→ sem naked exposure
```

### GT-06 — SHADOW_CHALLENGER

```text
mesmos input hashes
→ champion executa
→ challenger shadow
→ zero live side effect
→ disagreement evidence
```

### GT-07 — DETERMINISTIC_REPLAY

```text
same source bytes
+ same inputs
+ same policies
+ same seeds/events
→ same state hashes
→ same release hashes
```

---

## 17. Sequência correta de união

### Onda M0 — preservar as entregas

1. copiar os cinco ZIPs sem alteração;
2. registrar hashes e tamanhos;
3. criar `MERGE_INPUTS.json`;
4. marcar os packages de agente como históricos.

### Onda M1 — criar a árvore canônica

1. novo projeto `quant-pipeline-p8`;
2. um `pyproject.toml`;
3. um namespace;
4. uma API;
5. um version source;
6. um registry generator.

### Onda M2 — foundation/contracts

1. consolidar models, clocks, hashing e errors;
2. congelar os cinco contratos internos;
3. gerar schemas fechados;
4. publicar fixtures positivas e negativas.

### Onda M3 — transplantar source

Copiar a lógica produtiva das dez subfases para o layout canônico, sem copiar:

```text
build artifacts
agent meta packages
pyc/cache
private duplicated foundations
historical generated code
```

### Onda M4 — fechar fronteiras

Ordem:

```text
A1→A2
A2→A3
A3→A4
A4→A5
A5→A4
A5→P9/P0
```

### Onda M5 — migrar testes

1. todos os testes locais;
2. restaurar testes componentes do Agente 3;
3. pairwise handshakes;
4. contract tamper tests;
5. property/metamorphic tests.

### Onda M6 — golden threads

Executar os sete casos ponta a ponta.

### Onda M7 — release

1. uma wheel;
2. um ZIP;
3. clean install/extraction;
4. SBOM;
5. manifests;
6. deterministic replay;
7. P9/P0 consumers;
8. `production_promotion_allowed=false`.

---

## 18. O que pode ser unido agora

Pode ser unido imediatamente em uma branch de integração:

- source das dez subfases, em árvore única;
- documentação e planos;
- testes locais, após normalização de paths;
- registries como material de reconciliação;
- adapters e ports que não alterem semântica econômica;
- foundation do Agente 4 como referência de eventos/money;
- contracts do Agente 1 como referência das fronteiras iniciais;
- runtime safety do Agente 5 como referência da S9.

## O que não pode ser unido por simples cópia

- `pyproject.toml` de qualquer agente;
- root `__init__.py` do Agente 4 sem reescrita;
- cinco implementações de hashing;
- modelos homônimos `DecisionReadyRiskBundle`;
- saída A3 diretamente na API A4;
- comando runtime A4 atual como contrato final;
- manifests dos agentes como manifesto da release final;
- archives, `.pyc`, `.egg-info`, caches e build dirs;
- resultados de testes locais como prova de integração.

---

## 19. Estimativa de retrabalho por fronteira

| Trabalho | Natureza | Severidade |
|---|---|---:|
| Consolidar foundation/contracts | transversal | alta |
| A1→A2 consumer | integração + lineage | média/alta |
| A2→A3 risk bundle | contrato quantitativo | alta |
| A3→A4 target materialization | transformação econômica | crítica |
| A4→A5 evidence envelope | contrato/auditoria | média |
| A5→A4 runtime command | segurança stateful | crítica |
| Layout/import normalization | engenharia | média |
| Test suite normalization | engenharia | média |
| Release cleanup/manifests | release | média |

A transformação mais delicada é A3→A4. Ela determina se a decisão por candidato se transforma corretamente em posições físicas executáveis sem destruir o dual book.

---

## 20. Decisão final

```text
OS CINCO AGENTES PODEM SER UNIDOS: SIM
POR CÓPIA/INSTALAÇÃO DIRETA: NÃO
POR ÁRVORE CANÔNICA + CONTRACT BRIDGES: SIM
```

### Estado final da auditoria

```text
AGENT_1_LOCAL_QUALITY: PASS
AGENT_2_LOCAL_QUALITY: PASS
AGENT_3_LOCAL_INTEGRATION: PASS_LIMITED_TEST_SURFACE
AGENT_4_LOCAL_QUALITY: PASS
AGENT_5_DECLARED_LOCAL_QUALITY: PASS_NOT_REEXECUTED

SOURCE_COLOCATION: PASS
DEPENDENCY_INTERSECTION: PASS
PACKAGE_LAYOUT: REQUIRES_REWRITE
SHARED_FOUNDATION: NOT_CLOSED
A1_A2_HANDOFF: BLOCKED
A2_A3_HANDOFF: BLOCKED
A3_A4_HANDOFF: BLOCKED
A4_A5_HANDOFF: PARTIAL
A5_A4_RUNTIME: BLOCKED
P8_P9_REAL_CONSUMER: NOT_PROVEN
P8_P0_REAL_CONSUMER: NOT_PROVEN

DIRECT_MERGE: BLOCKED
CONTROLLED_INTEGRATION: APPROVED
PRODUCTION_PROMOTION_ALLOWED: FALSE
```

A melhor próxima entrega é uma **P8 Integration RC0**, não ainda uma release funcional final. Ela deve conter a árvore única, o foundation canônico, os contratos congelados e adapters estritos, preservando as implementações dos agentes enquanto fecha uma fronteira por vez.
