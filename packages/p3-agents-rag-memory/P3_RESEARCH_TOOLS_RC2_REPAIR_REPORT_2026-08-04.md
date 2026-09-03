# P3 Research Tools Unified RC2 — Relatório de Correção

Data: 2026-08-04  
Escopo: P3.S32–P3.S40, integração com P3.S1–P3.S31 e compatibilidade global RC4.1.

## Veredito

Os bloqueadores encontrados no RC1 foram corrigidos sem reescrever os algoritmos de domínio. A arquitetura resultante preserva a autoridade legada de 81 módulos e acrescenta uma superfície executável composta de 128 módulos, mantendo os 47 módulos de pesquisa como extensão explícita e auditável.

O release continua sem autoridade de promoção para produção: essa decisão pertence exclusivamente à P0. Os handoffs suplementares para P4 e P9 permanecem honestamente não materializados; no caso de P9, o contrato global RC4.1 proíbe uma conexão direta P3→P9, portanto a evidência N+1 é mantida localmente com status `DEFERRED_BY_GOVERNANCE`.

## Correções principais

### 1. Registry e executor

- `MODULE_REGISTRY`: preservado com 81 módulos legados.
- `RESEARCH_TOOLS_EXTENSION_MODULE_REGISTRY`: 47 módulos S32–S40.
- `EXECUTABLE_MODULE_REGISTRY`: composição de 128 módulos.
- `by_id()` e o executor público resolvem módulos legados e de extensão.
- CLI e validação de release verificam a composição 81 + 47 sem alterar contratos antigos.

### 2. Contratos e DAG

- S37.M01–M04 passaram a declarar inputs obrigatórios e opcionais corretamente.
- Registry, IO matrix, wrappers e contratos foram sincronizados.
- DAG regenerada com 47 nós, sem ciclos e sem arestas internas com artefatos inexistentes.
- A rota real S21.M03/M04 → S40.M04 foi declarada.
- Arestas falsas P3.S40.M06→P4 e P3.S40.M07→P9 foram removidas.
- Candidatos downstream são descritos separadamente e não representam conexões executáveis.

### 3. Fronteira point-in-time

Foi criada uma `BoundaryRuntimeFactory` que materializa, a partir do bundle S33 e de snapshots congelados:

- `pit_market_query_port`;
- `pit_macro_query_port`;
- `company_pit_query_port`;
- `quant_pit_query_port`;
- `corpus_repository`;
- ports genéricos de pesquisa, proveniência e resolução temporal quando disponíveis.

Objetos de processo permanecem em um `ProcessLocalRuntimeStore` injetado. Nenhum callable ou conexão viva é serializado no DAG.

### 4. Autoridade única S40.M01–M03

- M01 monta uma única instância imutável de `OperationRegistry`.
- M01 valida os 34 contratos de operação, aliases, ports, qualificações, readiness e hashes de evidência familiar.
- M02 recupera exatamente o registry de M01 e cria um único gateway process-local.
- M03 verifica hash do registry, snapshot da extensão, conjunto de operações, objeto runtime, providers, políticas de rede, entitlements e contextos.
- A superfície explícita `research_tool_operations` ficou restrita a testes opt-in e não pode sobrescrever operações canônicas.

### 5. Evidência, qualificação e release

- M04 consome resultados reais do S21.
- M05 torna completeness, preflight, receipts de integração, leakage e replay bloqueantes.
- M06 valida operações e modos contra registries canônicos antes de produzir o candidato P4.
- M07 exige commitment anterior ao outcome, prova de cutoff e `N_PLUS_1_ONLY`.
- M08 verifica que matriz, leakage, completeness, preflight e manifests downstream pertencem à mesma cadeia de hashes.
- O release gate permanece fail-closed e sem autoridade de promoção.

### 6. Governança P4/P9

O contrato global RC4.1 permite P3→P4 apenas para os artefatos compartilhados já registrados e proíbe P3→P9 diretamente.

Por isso:

- o painel de processo para P4 é um candidato suplementar, não uma aresta ativa;
- a evidência de aprendizado destinada conceitualmente a P9 fica local;
- o status P9 é `DEFERRED_BY_GOVERNANCE`;
- qualquer transferência futura exige intermediário autorizado ou alteração formal do contrato global pela P0;
- feedback permanece exclusivamente N+1.

## Estado dos 18 módulos anteriormente vermelhos

| Módulo/grupo | Correção RC2 | Estado |
|---|---|---|
| S33.M05 | fábrica de ports process-local | corrigido |
| S35.M02/M05 | policy e budget consumidos; dependências explícitas | corrigido |
| S36.M06 | qualification/readiness chegam ao registry | corrigido |
| S37.M01–M04 | contratos required/optional normalizados | corrigido |
| S38.M06 | readiness e branch qualification preservadas | corrigido |
| S39.M04 | qualificação metodológica participa do gate | corrigido |
| S40.M01 | registry único; dependências e hashes completos | corrigido |
| S40.M02 | consome o registry de M01; não reconstrói autoridade | corrigido |
| S40.M03 | contrato, preflight e hashes convergentes | corrigido |
| S40.M04 | rota real após execução S21 | corrigido |
| S40.M05 | completeness/preflight/receipts bloqueantes | corrigido |
| S40.M06 | IDs e modos validados; P4 não ligado falsamente | corrigido |
| S40.M07 | cutoff, commitment, N+1 e governança P9 | corrigido |
| S40.M08 | integridade completa da cadeia de release | corrigido |

## Critérios finais

- 81 módulos legados preservados.
- 47 módulos de extensão descobertos pelo executor.
- 128 contratos executáveis carregados.
- 34 operações de pesquisa com uma autoridade de registry.
- DAG interna acíclica e consistente.
- Sem estado global oculto para registry/gateway.
- Sem rede viva em backtest.
- Sem ligação direta P3→P5/P6/P7/P8/P9.
- P0 continua sendo a única autoridade de promoção.

## Resultado de testes

A auditoria final executa a suíte completa, verificação de imports sem dependências opcionais, compilação, validação de contratos, schemas, hashes, mirrors e extração limpa do ZIP. O comprovante final é registrado no `RELEASE.json` e nos manifests gerados pelo `tools/release.py`.

## Fechamento de validação

A matriz final executada em processos independentes passou **905/905 testes**: 312 de núcleo/contratos/integração, 227 phase-specific, 66 research-tools, 278 de runtime e 22 de avaliação/especificações/final integration. O registry preserva 81 módulos legados e oferece 128 módulos executáveis. A DAG S32–S40 possui 47 nós, 123 arestas internas válidas e nenhum ciclo.

O relatório detalhado está em `P3_RESEARCH_TOOLS_UNIFIED_RC2_VALIDATION.md`.
