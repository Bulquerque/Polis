# P3 Research Tools Extension — Agente 3
## Plano profundo de implementação para P3.S38–P3.S40

**Versão:** 1.0.0  
**Responsável:** Agente 3  
**Escopo congelado:** `P3.S38`, `P3.S39`, `P3.S40`  
**Quantidade:** 3 subfases, 18 módulos  
**Regra principal:** nenhuma alteração nos módulos canônicos `P3.S1–P3.S31`.

---

# 1. Veredito após auditoria do pacote

O Agente 3 não é apenas responsável por “fundamentos e cálculos”. Ele é o ponto em que a extensão precisa provar que consegue:

1. implementar ferramentas reais sem fabricar dados ausentes;
2. integrar handlers dos três agentes no `ToolGatewayPort` já aceito pelo S21;
3. preservar a validação existente do S21;
4. transformar evidências internas em referências reconhecidas pelo `P3.S21.M04`;
5. exportar resultados suplementares sem quebrar P4, P5 ou P9;
6. emitir qualificação e evidência para P0, sem se autopromover.

A auditoria encontrou cinco restrições que mudam o desenho da implementação.

## 1.1 Os contratos antigos da P3 aceitam IDs apenas até S31

`contracts/base.py` restringe `producer_module_id` a `P3.S1–P3.S31`. Como os módulos antigos não serão modificados, `S38–S40` não devem reutilizar diretamente `ArtifactPointer` ou `LineageRecord` dessa autoridade quando o produtor for um módulo novo.

**Decisão:** o Agente 3 consumirá o pacote de contratos da extensão fornecido pelo Agente 1, com `ExtensionLineageRecord` e `ExtensionArtifactPointer` autorizando `P3.S32–P3.S40`. Conversões para modelos antigos ficam apenas na camada de compatibilidade de S40.

## 1.2 P2 não possui fundamentos estruturados suficientes

A P2 materializa filings como documentos, mas não fornece atualmente painéis canônicos completos de:

- demonstrações financeiras as-reported;
- fatos XBRL normalizados;
- segmentos;
- guidance;
- pares;
- histórico de restatements;
- alocação de capital estruturada.

**Decisão:** `P3.S38` será implementada integralmente como arquitetura e handlers, mas a prontidão será determinada por operação e modo. Operações sem dados ficam `BLOCKED_UPSTREAM`; nenhuma resposta é sintetizada por LLM para parecer disponível.

## 1.3 O S21 só aceita evidências conhecidas no RetrievalEvidenceMap

`P3.S21.M04` rejeita `evidence_refs` que não estejam no `RetrievalEvidenceMap`, exceto a referência sintética `tool:<execution_id>`.

**Decisão:** `P3.S40.M04` será inserido entre `P3.S21.M03` e `P3.S21.M04`. Ele produzirá um `extended_retrieval_evidence_map` no schema exato do S21, combinando:

- evidências RAG existentes;
- evidências provenientes das ferramentas;
- hashes e `available_at` das evidências.

O DAG entregará esse overlay ao `P3.S21.M04` sem modificar seu código.

## 1.4 P4 atual não consome o novo handoff

P4 exige os seis artefatos sociais existentes e não conhece `research_process_panel`.

**Decisão:** `P3.S40.M06` produz um handoff **suplementar, aditivo e não obrigatório**. A extensão não alegará que P4 RC4.1 já o consome. Uma futura alteração exclusiva da P4 poderá habilitá-lo sem quebrar o fluxo atual.

## 1.5 P9 atual também não consome a evidência nova

P9 RC4.1 recebe P8 e gera feedback para P3; seu contrato de entrada não inclui a nova evidência de ferramentas.

**Decisão:** `P3.S40.M07` gera um pacote consumer-ready para uma futura integração P9. O release report deve declarar `PRODUCER_READY_CONSUMER_NOT_YET_WIRED`, nunca `CONSUMED`.

---

# 2. Limites de autoridade do Agente 3

## 2.1 O Agente 3 pode alterar

```text
extensions/research_tools/families/company/
extensions/research_tools/families/quant/
extensions/research_tools/runtime/
extensions/research_tools/evidence/
extensions/research_tools/qualification/
modules/P3_S38_*.py
modules/P3_S39_*.py
modules/P3_S40_*.py
contracts/modules/P3_S38_*.yaml
contracts/modules/P3_S39_*.yaml
contracts/modules/P3_S40_*.yaml
schemas/research_tools/company/
schemas/research_tools/quant/
schemas/research_tools/runtime/
tests/research_tools/company/
tests/research_tools/quant/
tests/research_tools/runtime/
```

## 2.2 O Agente 3 não pode alterar

- módulos `P3.S1–P3.S31`;
- contratos compartilhados congelados pelo Agente 1;
- fronteira P1/P2 implementada pelo Agente 1;
- handlers de corpus, mercado, opções ou macro do Agente 2;
- contratos P4, P5 ou P9 nesta entrega;
- decisões de promoção da P0;
- dados da P1/P2.

## 2.3 Dependências públicas permitidas

Do Agente 1:

```text
ResearchToolModel
ResearchToolCallContext
ResearchToolRequest
ResearchToolResultEnvelope
ResearchEvidenceRef
PitQueryProof
CoverageReport
ProvenanceReport
ExecutionReport
OperationSpec
ResearchModeSpec
HandlerBundle
HandlerRegistryPort
PitResearchQueryPort
RawEvidenceResolverPort
TemporalEntityResolverPort
ResearchEvidenceStorePort
```

Do Agente 2:

```text
corpus_tool_handler_bundle
market_tool_handler_bundle
options_tool_handler_bundle
macro_tool_handler_bundle
operation_mode_qualification reports
```

Importar módulos internos de outro agente é proibido.

---

# 3. Compatibilidade com as outras fases

| Fase/bloco | Relação com Agente 3 | Regra de compatibilidade |
|---|---|---|
| P1 | Custódia de bytes e snapshots | acesso apenas por `RawEvidenceResolverPort` e referência autorizada pela P2 |
| P2 | Autoridade de semântica e PIT | S38/S39 consultam somente `PitResearchQueryPort` do Agente 1 |
| P3.S15/S16 | catálogo e entitlement antigos | S40 consome overlays do Agente 1; não reinterpreta contratos antigos |
| P3.S20 | contexto da persona | descritores vêm de S34; S40 não monta prompt |
| P3.S21.M03 | executa gateway | S40 implementa `ToolGatewayPort` e preserva provider ID |
| P3.S21.M04 | valida schema/PIT/evidence | S40.M04 cria overlay de evidências antes desse módulo |
| P3.S22 | liga crenças a evidências | usa resultados validados existentes; nenhuma alteração |
| P3.S27 | métricas de uso | continua consumindo `tool_call_audit_panel`; métricas adicionais ficam no S40 |
| P3.S30/S31 | handoffs antigos | permanecem intactos; novos handoffs são suplementares |
| P4 | futura consumidora de métricas de pesquisa | producer-ready, consumo não ativado no RC4.1 |
| P5 | consumidora indireta via P4 | nenhum acesso ou handoff direto |
| P9 | futura avaliadora de utilidade da pesquisa | pacote preparado, mas consumidor RC4.1 não está conectado |
| P0 | única autoridade de promoção | S40 emite evidência; não promove a si próprio |

---

# 4. Estrutura de código do Agente 3

```text
extensions/research_tools/
├── families/
│   ├── company/
│   │   ├── readiness.py
│   │   ├── profile.py
│   │   ├── statements.py
│   │   ├── statement_versions.py
│   │   ├── earnings_quality.py
│   │   ├── capital_allocation.py
│   │   ├── guidance.py
│   │   ├── peers.py
│   │   ├── valuation.py
│   │   ├── handlers.py
│   │   └── qualification.py
│   └── quant/
│       ├── returns.py
│       ├── volatility.py
│       ├── drawdown.py
│       ├── dependence.py
│       ├── entropy.py
│       ├── event_window.py
│       ├── scenario.py
│       ├── handlers.py
│       └── qualification.py
├── runtime/
│   ├── handler_registry.py
│   ├── alias_resolution.py
│   ├── dispatcher.py
│   ├── execution.py
│   ├── gateway.py
│   ├── result_mapping.py
│   ├── binding.py
│   └── preflight.py
├── evidence/
│   ├── tool_evidence_map.py
│   ├── retrieval_overlay.py
│   ├── process_panel.py
│   ├── p4_handoff.py
│   └── p9_learning.py
└── qualification/
    ├── operation_matrix.py
    ├── temporal_leakage.py
    ├── contract_evidence.py
    ├── receipts.py
    └── release_gate.py
```

Não serão criados `utils.py`, `helpers.py`, `common.py`, mega-factories ou classes-base de ferramenta.

---

# 5. P3.S38 — Company Fundamentals Tool Suite

## 5.1 Missão

Oferecer a família `company.fundamentals.v1` com operações tipadas, determinísticas e condicionadas à disponibilidade real de dados estruturados.

## 5.2 Operações públicas

```text
get_profile
get_financial_statements
get_fundamental_snapshot
get_guidance
get_capital_allocation
get_peers
calculate_valuation
```

## 5.3 Modos

```text
QUICK_CHECK
STANDARD_REVIEW
DEEP_QUALITATIVE
ACCOUNTING_QUALITY
FORENSIC
```

`DEEP_QUALITATIVE` e `ACCOUNTING_QUALITY` são ramos paralelos. `FORENSIC` exige versões/restatements.

## 5.4 Estado inicial provável por operação

| Operação | Estado inicial esperado | Condição |
|---|---|---|
| `get_profile` | `DEGRADED` | pode usar documentos/identidade; só vira `AVAILABLE` com view estruturada |
| `get_financial_statements` | `BLOCKED_UPSTREAM` | exige facts e statements estruturados |
| `get_fundamental_snapshot` | `BLOCKED_UPSTREAM` | exige fatos financeiros normalizados |
| `get_guidance` | `DEGRADED` ou `BLOCKED_UPSTREAM` | documental apenas se tipagem confiável existir |
| `get_capital_allocation` | `DEGRADED` | corporate actions + documentos; métricas avançadas bloqueadas |
| `get_peers` | `BLOCKED_UPSTREAM` | exige autoridade temporal de pares |
| `calculate_valuation` | `AVAILABLE` como calculadora de cenário | exige premissas explícitas e fatos referenciados; nunca gera recomendação |

---

## P3.S38.M01 — `company_operation_readiness_gate_builder`

### Responsabilidade

Determinar disponibilidade por combinação:

```text
operation_id × mode_id × required_view
```

### Entradas

```text
research_tool_extension_snapshot
company operation specs
research_mode_registry
research_data_boundary_bundle
phase2_research_view_manifest
company_readiness_policy_config
```

### Saídas

```text
company_operation_readiness_panel
company_data_gap_report
```

### Record principal

```text
tool_id
operation_id
mode_id
status
required_views
available_views
missing_views
quality_floor_met
pit_fields_present
version_history_available
reason_codes
```

### Algoritmo

1. carregar specs da família;
2. consultar apenas metadata das views;
3. verificar schemas, hashes e quality status;
4. verificar campos PIT obrigatórios;
5. verificar cobertura de versões quando exigida;
6. resolver `AVAILABLE`, `DEGRADED` ou `BLOCKED_UPSTREAM`;
7. não ler conteúdo empresarial neste módulo.

### Não responsabilidades

- não executar handlers;
- não inferir dados ausentes;
- não liberar operação pela existência de documentos genéricos;
- não transformar `DEGRADED` em `AVAILABLE` por configuração.

### Testes

- operação sem view fica bloqueada;
- view com schema incorreto fica bloqueada;
- modo básico disponível e modo forense bloqueado;
- redução da qualidade nunca melhora status;
- saída determinística diante de reordenação das views.

---

## P3.S38.M02 — `company_profile_filing_xbrl_handler_bundle_builder`

### Responsabilidade

Construir handlers de `get_profile` e os componentes de leitura de fatos empresariais estruturados usados pelos módulos seguintes.

### Entradas

```text
company_operation_readiness_panel
research_data_boundary_bundle
temporal_entity_resolution service
company_profile_policy_config
```

### Saídas

```text
company_profile_filing_handler_bundle
company_profile_handler_qualification_report
```

### Regra crítica

A P3 não será um parser XBRL upstream. Este módulo apenas consulta facts XBRL já normalizados pela P2 quando existirem. Arelle, SEC ou APIs externas não são chamados em backtest.

### `get_profile`

Pode retornar somente campos com vigência e proveniência:

```text
entity_id
legal_name
trading_names
sector/industry quando disponível
country
instrument_refs
segment_refs
effective_from/effective_to
evidence_refs
```

### Falhas

```text
P3RT-UPSTREAM-COMPANY-PROFILE-MISSING
P3RT-DATA-ENTITY-AMBIGUOUS
P3RT-PIT-PROFILE-VERSION-FUTURE
P3RT-DATA-XBRL-FACTS-UNAVAILABLE
```

### Testes

- profile atual não substitui profile histórico;
- entidade ambígua não é escolhida silenciosamente;
- documento sem estrutura gera `DEGRADED`, não facts fabricados;
- nenhuma chamada de rede em replay.

---

## P3.S38.M03 — `as_reported_financial_statement_handler_bundle_builder`

### Responsabilidade

Implementar `get_financial_statements`, preservando versões as-reported e restatements.

### Entradas

```text
company_operation_readiness_panel
research_data_boundary_bundle
company statement policy
statement concept mapping registry
```

### Saídas

```text
financial_statement_handler_bundle
statement_semantics_manifest
```

### Contrato de fato financeiro

```text
entity_id
statement_type
concept_id
period_start
period_end
instant_date
fiscal_period
value
unit
currency
consolidation_scope
filing_id
filing_version
published_at
available_at
restates_filing_id
source_id
lineage_id
```

### Invariantes

- valor republicado não apaga o original;
- `period_end` não equivale a `available_at`;
- conceitos diferentes não são fundidos apenas por label;
- unidades e escalas são explícitas;
- `FORENSIC` exige histórico de versões;
- registros futuros são filtrados antes da agregação.

### Testes

- consulta anterior a um restatement devolve o valor original;
- consulta posterior pode devolver ambas as versões com relação explícita;
- unidade incompatível falha;
- duplicidade de fato é detectada;
- `as_of` menor não aumenta statements visíveis.

---

## P3.S38.M04 — `earnings_quality_capital_allocation_handler_bundle_builder`

### Responsabilidade

Implementar:

```text
get_fundamental_snapshot
get_capital_allocation
```

### Entradas

```text
financial_statement_handler_bundle
corporate action views
company formula registry
company operation readiness
research_data_boundary_bundle
```

### Saídas

```text
earnings_quality_capital_allocation_handler_bundle
company_formula_registry_manifest
```

### Fórmulas permitidas

Somente fórmulas determinísticas e versionadas, por exemplo:

- crescimento e margens;
- conversão lucro-caixa;
- accruals declarados;
- capital de giro;
- dívida e cobertura;
- capex;
- dividendos e recompras;
- emissão/diluição;
- reinvestimento;
- retorno incremental sobre capital quando dados suficientes existirem.

### Regras

- nenhuma métrica é calculada se faltarem componentes materiais;
- missingness é parte do resultado;
- itens extraordinários não são removidos silenciosamente;
- não existe score universal de “empresa boa”;
- não existe recomendação de investimento.

### Testes

- fórmulas contra fixtures manuais independentes;
- escala monetária incorreta falha;
- componente ausente produz `DEGRADED` e coverage explícita;
- corporate action não anunciada é rejeitada;
- mesma entrada gera mesmo hash.

---

## P3.S38.M05 — `guidance_peers_valuation_handler_bundle_builder`

### Responsabilidade

Implementar:

```text
get_guidance
get_peers
calculate_valuation
```

O wrapper compõe serviços pequenos; não concentra toda a lógica em um arquivo.

### Entradas

```text
company operation readiness
research_data_boundary_bundle
guidance policy
peer authority policy
valuation method registry
company profile/statement handlers
market views quando autorizadas
```

### Saídas

```text
guidance_peers_valuation_handler_bundle
valuation_method_registry_manifest
```

### Guidance

Preservar:

```text
metric
lower/upper bound
horizon
unit
published_at
available_at
revision_of
withdrawn_at
```

### Pares

- pares documentados ou autoridade temporal;
- sugestões algorítmicas são marcadas como `SUGGESTED`, não canônicas;
- conjunto atual de pares não é aplicado automaticamente ao passado.

### Valuation

Métodos iniciais:

```text
observed_multiples
historical_band
peer_band
scenario_dcf
reverse_dcf
sensitivity_grid
```

Regras:

- premissas sempre explícitas;
- fatos usados possuem evidence refs;
- resultados são `scenario_value`, nunca `target_price` ou sinal;
- ferramenta não otimiza premissas para justificar a tese;
- nenhuma extrapolação é escondida.

### Testes

- DCF com fixture analítica;
- reverse DCF recupera premissa conhecida;
- peer set futuro é rejeitado;
- guidance revisado respeita `available_at`;
- payload não contém campos proibidos de sinal/decisão.

---

## P3.S38.M06 — `company_tool_bundle_branch_qualification_builder`

### Responsabilidade

Consolidar handlers e qualificar cada operação/modo.

### Entradas

```text
handler bundles M02–M05
company_operation_readiness_panel
operation/mode specs
company contract test reports
company PIT/leakage reports
```

### Saídas

```text
company_tool_handler_bundle
company_operation_mode_qualification
company_qualification_evidence_package
```

### Status

```text
QUALIFIED_LOCAL
DEGRADED
BLOCKED_UPSTREAM
FAILED
```

### Gate

Uma operação pode entrar no catálogo efetivo apenas se:

- handler registrado;
- schemas válidos;
- dados prontos;
- testes PIT passam;
- fórmulas qualificadas;
- evidência de provenance existe.

`BLOCKED_UPSTREAM` é aceitável no pacote, mas a operação não pode ser mostrada ao agente.

---

# 6. P3.S39 — Quantitative Diagnostic Tool Suite

## 6.1 Missão

Implementar cálculos descritivos pequenos, puros e auditáveis, sem duplicar P4/P5/P8/P9.

## 6.2 Operações

```text
return_statistics
realized_volatility
drawdown
correlation
entropy
event_window
scenario_shock
```

## 6.3 Modos

```text
BASIC
ROBUST
STABILITY
```

## 6.4 Proibições

- backtest;
- seleção de feature;
- seleção de modelo;
- busca da melhor janela;
- sinal;
- ranking;
- portfólio;
- consulta a P5;
- uso de dados depois de `decision_time`.

---

## P3.S39.M01 — `return_risk_volatility_handler_bundle_builder`

### Responsabilidade

Implementar:

```text
return_statistics
realized_volatility
drawdown
```

### Entradas

```text
research_data_boundary_bundle
quant method policy
frequency/annualization registry
operation/mode specs
```

### Saídas

```text
return_risk_volatility_handler_bundle
return_volatility_method_manifest
```

### Métodos

#### Return statistics

- retorno simples e log, conforme request;
- média, mediana, dispersão e quantis declarados;
- número de observações e missingness;
- frequência não é inferida silenciosamente.

#### Realized volatility

`BASIC`:

- close-to-close;
- anualização declarada.

`ROBUST`:

- diagnósticos de outlier;
- Parkinson/Garman-Klass somente com OHLC completo;
- comparação entre estimadores, sem escolher “o melhor”.

`STABILITY`:

- múltiplas janelas declaradas;
- bootstrap/intervalos;
- sensibilidade.

#### Drawdown

- wealth index iniciado explicitamente;
- peak, trough, recovery;
- current drawdown;
- sem usar valores após `decision_time`.

### Testes

- séries constantes;
- preços negativos/zero quando inválidos;
- missingness;
- frequência irregular;
- comparação com cálculos independentes;
- dados futuros não alteram resultado passado.

---

## P3.S39.M02 — `dependence_entropy_handler_bundle_builder`

### Responsabilidade

Implementar:

```text
correlation
entropy
```

### Entradas

```text
research_data_boundary_bundle
dependence method policy
entropy discretization registry
operation/mode specs
```

### Saídas

```text
dependence_entropy_handler_bundle
dependence_entropy_method_manifest
```

### Correlação

- Pearson e Spearman;
- alinhamento explícito de calendários;
- mínimo de observações;
- janelas móveis declaradas;
- bootstrap em `STABILITY`;
- sem busca automática de lag maximizador.

### Entropia

- Shannon com bins versionados;
- permutation entropy quando aplicável;
- sensibilidade à discretização;
- política de bins congelada no snapshot;
- nenhuma discretização escolhida pelo resultado.

### Testes

- invariância à reordenação após alinhamento;
- correlação com série constante gera status explícito;
- bins idênticos produzem hash idêntico;
- aumentar dados futuros não muda cálculo histórico;
- amostra insuficiente é `DEGRADED`, não NaN silencioso.

---

## P3.S39.M03 — `event_window_scenario_handler_bundle_builder`

### Responsabilidade

Implementar:

```text
event_window
scenario_shock
```

### Entradas

```text
research_data_boundary_bundle
event views
market/benchmark views
scenario method policy
operation/mode specs
```

### Saídas

```text
event_window_scenario_handler_bundle
event_scenario_method_manifest
```

### Event window

- evento precisa ter `available_at`;
- janela pós-evento só é calculada quando seu fim está no passado;
- benchmark adjustment explícito;
- placebos somente entre datas já conhecidas;
- não declara causalidade.

### Scenario shock

- choques e coeficientes são entradas explícitas;
- coeficientes estimados usam somente amostra anterior;
- ferramenta calcula, não atribui probabilidade;
- saída é cenário condicional, não previsão.

### Testes

- evento futuro bloqueado;
- janela incompleta bloqueada;
- timezone e calendário;
- placebo não cruza `decision_time`;
- cenário linear com solução analítica;
- nenhuma busca de choque “mais lucrativo”.

---

## P3.S39.M04 — `quant_tool_bundle_method_qualification_builder`

### Responsabilidade

Consolidar handlers e qualificar métodos.

### Entradas

```text
handler bundles M01–M03
operation/mode specs
quant unit/contract/property reports
quant leakage reports
```

### Saídas

```text
quant_tool_handler_bundle
quant_operation_mode_qualification
quant_qualification_evidence_package
```

### Gates

- método e parâmetros versionados;
- nenhuma autoridade proibida;
- resultados finitos ou status explícito;
- testes diferenciais e metamórficos;
- PIT proof presente;
- aliases legados produzem o mesmo result hash.

---

# 7. P3.S40 — Runtime Composition, Evidence, Qualification & Downstream

## 7.1 Missão

Ser o composition root da extensão e a única ponte operacional com o S21, sem absorver lógica de domínio.

## 7.2 Lanes internas

```text
Bootstrap:       M01–M03
Entre S21.M03/M04: M04
Qualification:   M05
Post-cognition:  M06–M07
Release:         M08
```

---

## P3.S40.M01 — `internal_handler_registry_assembler`

### Responsabilidade

Registrar todos os handlers disponíveis.

### Entradas

```text
tool_operation_registry
compatibility_alias_registry
corpus/market/options/macro bundles do Agente 2
company bundle S38
quant bundle S39
operation qualification preliminar
```

### Saídas

```text
internal_handler_registry
handler_registry_completeness_report
```

### Invariantes

- uma chave `(tool_id, operation_id)` possui exatamente um handler;
- alias não possui handler próprio;
- handler extra não declarado é erro;
- operação local disponível sem handler é erro;
- registro imutável após construção;
- sem import side effects.

### Testes

- duplicidade;
- handler ausente;
- alias circular;
- hash estável;
- reordenação dos bundles não muda registry.

---

## P3.S40.M02 — `composite_tool_gateway_runtime_factory`

### Responsabilidade

Criar o adapter que implementa o `ToolGatewayPort` do S21.

### Entradas

```text
internal_handler_registry
research_data_boundary_bundle
provider_transport_overlay
MCP gateway policy overlay
extension snapshot
runtime ports
```

### Saídas serializadas

```text
composite_tool_gateway_binding_manifest
gateway_runtime_readiness_report
```

### Saída process-local

```python
CompositeResearchToolGateway(ToolGatewayPort)
```

O objeto é criado pelo composition root e injetado em `S21Runtime`; não é serializado como artefato.

### Fluxo

```text
ValidatedToolCallRequestRecord
→ provider identity check
→ alias resolution
→ mode resolution already authorized
→ handler lookup
→ execution context binding
→ handler execution
→ ResearchToolResultEnvelope validation
→ ToolExecutionResponse mapping
```

### Regras

- `request.as_of` deve ser igual ao `decision_time` do binding;
- provider de saída deve ser igual ao provider autorizado;
- backtest proíbe HTTP/MCP;
- timeout externo fica no S21; handler interno possui work budget;
- `available_at` é max evidence time ou `decision_time` para cálculo puro;
- response hash usa canonical JSON;
- payload contém envelope completo, não dados crus ilimitados.

---

## P3.S40.M03 — `s21_runtime_binding_preflight_builder`

### Responsabilidade

Provar que S21 pode executar a extensão antes do primeiro ciclo.

### Entradas

```text
composite gateway binding
provider registry projection
MCP gateway policy projection
extended entitlement panel
extended person context bundle
operation schemas
extension snapshot
```

### Saídas

```text
s21_research_tool_runtime_binding_manifest
s21_runtime_preflight_report
```

### Verificações

- provider `internal_research` registrado;
- tool providers habilitados;
- schemas Draft 2020-12 válidos;
- `allowed_tool_ids` e entitlements alinhados;
- operações funcionais corretas;
- máximo de cinco chamadas;
- nenhuma ferramenta bloqueada aparece no contexto;
- gateway implementa `ToolGatewayPort`;
- snapshot/hash coerente;
- rede desabilitada no replay.

### Testes

- provider ausente;
- entitlement/context divergentes;
- schema inválido;
- ferramenta bloqueada exposta;
- configuração live em replay;
- alias não resolvido.

---

## P3.S40.M04 — `tool_execution_evidence_envelope_builder`

### Responsabilidade

Fechar a compatibilidade de evidência entre ferramentas e `P3.S21.M04`.

### Posição no DAG

```text
P3.S21.M03
→ P3.S40.M04
→ P3.S21.M04
```

### Entradas

```text
raw_tool_result_panel
tool_call_audit_panel
original retrieval_evidence_map
extension snapshot
research evidence schemas
```

### Saídas

```text
research_tool_result_envelope_panel
research_tool_evidence_map
extended_retrieval_evidence_map
research_tool_execution_trace_panel
```

### Algoritmo

1. validar envelope dentro de `canonical_payload`;
2. extrair evidence records;
3. validar IDs, hashes, source quality e `available_at`;
4. confirmar que todas as refs do resultado possuem record;
5. converter cada `ResearchEvidenceRef` para `S21.EvidenceRef`;
6. unir ao `RetrievalEvidenceMap` original;
7. deduplicar por `evidence_id` e exigir igualdade de conteúdo;
8. gerar lineage e hashes do overlay.

### Regra crítica

Não usar apenas `tool:<execution_id>` quando houver evidência externa real. A referência sintética fica reservada para cálculos puros sem fonte externa.

### Testes

- evidence ref desconhecida;
- mesmo ID com hashes diferentes;
- evidence futura;
- merge determinístico;
- S21.M04 real aceita o overlay;
- S22 real consegue vincular a crença.

---

## P3.S40.M05 — `operation_mode_qualification_leakage_runner`

### Responsabilidade

Consolidar evidências de qualificação por:

```text
tool_id × operation_id × mode_id
```

### Entradas

```text
qualification reports S35–S39
S21 integration receipts
PIT/property/metamorphic test evidence
handler registry completeness
preflight report
real execution evidence fixtures
```

### Saídas

```text
operation_mode_qualification_matrix
research_tool_leakage_report
qualification_evidence_manifest
```

### Status

```text
QUALIFIED_LOCAL
DEGRADED
BLOCKED_UPSTREAM
FAILED
```

### Leakage suite mínima

- `decision_time` menor não aumenta visibilidade;
- adicionar dados futuros não muda resultado passado;
- restatement futuro não altera statement histórico;
- janela pós-evento incompleta é bloqueada;
- alias e ID canônico geram o mesmo resultado;
- cache de snapshot diferente não é reutilizado.

M05 não executa `pytest` dentro de produção; ele valida receipts e pode executar self-checks determinísticos pequenos.

---

## P3.S40.M06 — `research_process_panel_p4_handoff_builder`

### Responsabilidade

Produzir métricas do processo de pesquisa e um handoff suplementar para futura integração P4.

### Entradas

```text
validated_tool_result_panel
tool_call_audit_panel
research_tool_result_envelope_panel
structured/evidence-bound belief outputs
phase3_run_snapshot
operation/mode registries
```

### Saídas

```text
research_process_panel
phase4_research_process_handoff_manifest
p4_research_handoff_compatibility_report
```

### Grain

```text
run_id × cycle_id × cognition_transaction_id
```

### Campos

```text
person_id
subject/proposition refs
requested and executed modes
tool families/operations
visible call count
internal subquery count
cost units
source diversity
source quality mean
evidence coverage
counterevidence ratio
information latency
future records rejected
downgrades
truncation
belief refs
```

### Compatibilidade P4/P5

- sem `target`, `future_return`, `prediction`, `signal`, `rank`, `portfolio_weight`;
- não altera `phase4_social_handoff_manifest` existente;
- `consumer_status=PRODUCER_READY_CONSUMER_NOT_YET_WIRED` no RC4.1;
- P5 só poderá receber efeitos após P4 transformá-los em features.

---

## P3.S40.M07 — `p9_research_tool_learning_evidence_builder`

### Responsabilidade

Preparar evidência outcome-blind para avaliação posterior da utilidade de ferramentas.

### Entradas

```text
research_process_panel
belief_outcome_commitment_log
research_tool_execution_trace_panel
phase3_run_snapshot
model knowledge cutoff report quando disponível
```

### Saídas

```text
p9_research_tool_learning_evidence
p9_research_tool_learning_handoff_manifest
p9_consumer_compatibility_report
```

### Chaves de junção futura

```text
commitment_id
belief_proposal_id
cognition_transaction_id
tool_call_request_id
execution_id
person_id
underlying_id
proposition_id
horizon
matures_at
```

### Regras

- não inclui outcome ainda não maturado;
- não avalia desempenho;
- não propõe patch;
- não promove ferramenta;
- feedback só pode retornar em N+1;
- consumer status RC4.1 deve declarar que P9 ainda não está conectado.

---

## P3.S40.M08 — `research_tool_extension_release_gate`

### Responsabilidade

Emitir o gate final do pacote do Agente 3 e evidência consumível pela P0.

### Entradas

```text
handler registry completeness
S21 preflight
operation qualification matrix
leakage report
P4/P9 compatibility reports
contract/schema/test reports
code quality report
manifest/hash report
rollback report
```

### Saídas

```text
research_tool_extension_release_gate
research_tool_extension_evidence_package
research_tool_extension_blocking_issue_panel
```

### Status

```text
PASS
DEGRADED
BLOCKED_UPSTREAM
FAIL
```

### Semântica

- `PASS`: todas as operações expostas às personas estão qualificadas;
- `DEGRADED`: operações não essenciais estão explicitamente bloqueadas e removidas do catálogo efetivo;
- `BLOCKED_UPSTREAM`: nenhuma vertical útil pode operar por falta de dados;
- `FAIL`: contrato, PIT, evidência, handler, replay ou integração quebrados.

### Autoridade

O módulo nunca declara promoção produtiva. Ele declara somente readiness interno. A promoção permanece exclusiva da P0.

---

# 8. DAG detalhado do Agente 3

```text
S32/S33/S34 contract freeze
        │
        ├───────────────┐
        │               │
Agent 2 bundles      S38 + S39 bundles
        │               │
        └───────┬───────┘
                ▼
          S40.M01 registry
                ▼
          S40.M02 gateway
                ▼
          S40.M03 preflight
                ▼
        existing S21.M01/M02/M03
                ▼
          S40.M04 evidence overlay
                ▼
        existing S21.M04/M05/M06
                ▼
            existing S22
                ▼
          S40.M06 + S40.M07
                │
          S40.M05 qualification
                ▼
          S40.M08 release gate
```

M05 pode consumir execução real ou fixtures qualificadas, mas o release final só ocorre após M04 e integração vertical.

---

# 9. Padrões de código obrigatórios

## 9.1 Contratos e tipos

- Pydantic estrito para dados serializados;
- dataclasses congeladas com slots para serviços process-local;
- `dict[str, Any]` apenas em wrappers e adaptação S21;
- nenhum modelo compartilhado duplicado;
- enums e reason codes do pacote congelado do Agente 1.

## 9.2 Funções

- uma função, uma regra;
- alvo de 30 linhas; revisão obrigatória acima de 50;
- complexidade até 8; revisão acima de 12;
- algoritmos matemáticos como funções puras;
- sem `datetime.now()` no domínio;
- sem random sem seed;
- sem `except Exception` no domínio.

## 9.3 Arquivos

- wrappers canônicos até 50 linhas úteis;
- serviços entre 80–200 linhas;
- revisão obrigatória acima de 300;
- nenhum arquivo gigante para S38.M05 ou S40.M02;
- composição por funções/objetos pequenos, não herança profunda.

## 9.4 Dependências

- bibliotecas mínimas;
- NumPy opcional apenas se já disponível; implementação de referência deve ser testável sem stack pesada;
- sem LangChain, Haystack, Neo4j, Redis ou MCP obrigatório;
- sem Arelle/QuantLib obrigatórios no runtime P3;
- nenhuma rede em TEST/REPLAY.

## 9.5 Observabilidade

Eventos:

```text
handler.request_received
handler.authorization_confirmed
handler.data_loaded
handler.pit_filtered
handler.computation_completed
handler.result_validated
evidence.overlay_built
gateway.response_mapped
qualification.operation_decided
```

Dimensões:

```text
run_id
cycle_id
person_id
request_id
execution_id
tool_id
operation_id
requested_mode
executed_mode
decision_time
snapshot IDs
records scanned/visible/rejected
request/result hashes
reason codes
```

---

# 10. Estratégia de testes

## 10.1 S38

- unitários de fórmulas;
- fixtures as-reported/restatement;
- contratos de readiness;
- propriedade temporal;
- missingness e unidades;
- ausência de campos proibidos;
- consumidores do S40.

## 10.2 S39

- testes analíticos independentes;
- differential tests;
- property-based;
- metamórficos;
- séries degeneradas;
- calendários irregulares;
- janela de evento incompleta;
- no-future-data invariants.

## 10.3 S40

- registry completeness;
- alias equivalence;
- gateway/S21 real;
- evidence overlay/S21.M04 real;
- S22 evidence binding real;
- concurrency e ordenação determinística;
- retry semantics preservadas pelo S21;
- P4/P9 compatibility reports;
- replay byte-identical;
- P0 evidence package.

## 10.4 Teste vertical obrigatório

```text
P2 clean_underlying_panel
→ S33 query port
→ quant.realized_volatility
→ S40 gateway
→ S21.M03 raw result/audit
→ S40.M04 evidence overlay
→ S21.M04 validated result
→ S21.M05 final claim citing execution
→ S22 evidence binding
→ S40 research process panel
```

Uma segunda vertical deve usar um documento/filing e uma operação `DEGRADED` ou `BLOCKED_UPSTREAM` de S38 para provar que o sistema não fabrica sucesso.

---

# 11. Riscos e respostas

| Risco | Resposta de projeto |
|---|---|
| P2 sem fatos financeiros | readiness por operação; handlers bloqueados; sem síntese |
| Evidências da tool rejeitadas pelo S21 | S40.M04 cria `extended_retrieval_evidence_map` |
| S40 virar monólito | separar registry, gateway, mapping, evidence, qualification e handoffs |
| Duplicar matemática da P4/P5 | limitar S39 a diagnósticos descritivos |
| Valuation virar sinal | usar cenário, premissas explícitas e campos não preditivos |
| P4/P9 não consumirem | emitir handoff suplementar com status honesto |
| Registros atuais contaminarem backtest | boundary S33 + proof PIT por resultado |
| Alias produzir resultado diferente | teste de equivalência de hash |
| Operation blocked aparecer ao LLM | preflight e entitlement gate falham |
| S40 se autopromover | release gate interno; P0 mantém autoridade |

---

# 12. Ordem de produção do Agente 3

## Marco 1 — Contratos e stubs

1. receber contract pack 1.0.0 do Agente 1;
2. criar estrutura de diretórios;
3. implementar modelos internos não serializados;
4. entregar stubs `BLOCKED_UPSTREAM` para S38;
5. entregar stubs determinísticos para S39;
6. criar esqueleto S40 M01–M04.

## Marco 2 — Quant vertical

1. implementar S39.M01;
2. integrar no registry/gateway;
3. fechar evidence overlay;
4. passar vertical S21/S22;
5. implementar M02/M03;
6. fechar M04.

## Marco 3 — Company readiness e operações viáveis

1. implementar S38.M01;
2. implementar `get_profile` documental degradado;
3. implementar valuation calculator de cenário;
4. manter statements/peers/forensic bloqueados até views reais;
5. qualificar M06.

## Marco 4 — Integração completa

1. integrar bundles do Agente 2;
2. fechar S40.M01–M04;
3. gerar M06/M07;
4. fechar qualification matrix M05;
5. emitir release gate M08;
6. rodar testes antigos e novos;
7. gerar manifestos/hashes/rollback evidence.

---

# 13. Definition of Done do Agente 3

O trabalho está concluído somente quando:

1. os 18 módulos existem com wrapper, contrato, schema, documentação e testes;
2. nenhum arquivo de implementação S1–S31 foi alterado;
3. todas as operações expostas possuem handler único;
4. toda operação não disponível está removida do contexto do agente;
5. o gateway real implementa o `ToolGatewayPort` existente;
6. o provider ID é preservado;
7. o S21.M04 aceita evidências reais através do overlay;
8. o S22 vincula crenças aos resultados de tools;
9. quant diagnostics não fazem backtest, seleção ou sinal;
10. company tools não fabricam dados upstream ausentes;
11. P4/P9 reports declaram honestamente o estado do consumidor;
12. nenhuma conexão direta P3→P5 existe;
13. replay idêntico produz hashes idênticos;
14. leakage suite passa;
15. os testes atuais da P3 continuam passando;
16. P0 recebe evidência, mas a P3 não se promove.

---

# 14. Decisão final

O Agente 3 deve priorizar primeiro a **vertical quant completa**, porque ela pode usar dados P2 já existentes e provar toda a integração S40→S21→S22. A família de fundamentos deve ser implementada com arquitetura completa e disponibilidade honesta por operação, não como uma camada de prompts que inventa balanços.

A parte mais crítica tecnicamente é `P3.S40.M04`: sem o overlay de evidências, os resultados das novas ferramentas podem executar, mas serão rejeitados pelo validador real do S21. Essa ponte deve ser tratada como bloqueador de release, não como detalhe posterior.
