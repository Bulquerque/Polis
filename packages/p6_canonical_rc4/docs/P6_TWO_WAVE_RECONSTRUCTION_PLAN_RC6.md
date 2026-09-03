# P6 — Plano de Reconstrução em Duas Ondas

## Baseline real

- Baseline recomendada: `P6_COMPLETE_DOMAIN_ORGANIZED_RC5_10.zip`
- SHA-256 real: `04a638b2c3597f99588305d35eb5e2a9229d55e44b35316196f80610d6054d6a`
- Estado atual verificado: 6 subfases, 18 módulos, arquitetura por domínio.
- A RC5.9 deve ser usada apenas como referência histórica de paridade.

## Decisão arquitetural

Adotar formalmente dez subfases. A funcionalidade-alvo contém dez domínios distintos e comprimi-los em seis subfases criaria novamente módulos monolíticos.

1. P6.S1 — Boundary and Market Snapshot
2. P6.S2 — Canonical Strategy Domain
3. P6.S3 — Template Generation
4. P6.S4 — Mutation and Deformation
5. P6.S5 — Target Payoff and Market-Implied State
6. P6.S6 — Inverse Design and Solver Portfolio
7. P6.S7 — Pricing, Greeks and Scenario Evaluation
8. P6.S8 — Feasibility and Defined-Risk Gate
9. P6.S9 — Canonicalization, Equivalence and Quality-Diversity
10. P6.S10 — Qualification, Publication and P7 Handoff

A organização do código deve ser por domínio e subfase. Não incluir agentes em namespaces, contratos, schemas, manifests ou documentação canônica.

## Onda 1 — Candidate Foundation

### Objetivo

Entregar um motor CPU-first de geração por templates, com contratos reais, PIT, payoff matematicamente reconciliado, risco definido, custos, liquidez, canonicalização e publicação auditável.

### Escopo obrigatório

- Auditoria profunda da RC5.10 e golden parity da funcionalidade preservada.
- Um único domínio canônico para instrumentos, contratos, quotes, pernas, estratégias, cenários, risco e lineage.
- Envelope canônico, hashing e serialização únicos.
- P6.S1 completa.
- P6.S2 completa.
- P6.S3 com Release 1 de templates.
- P6.S7 com entry price, payoff terminal, Greeks básicos e cenários nominais.
- P6.S8 com structural gate, maximum-loss proof, cost/liquidity/data-quality gates.
- P6.S9 com canonicalização, fingerprints, equivalência exata/por escala e deduplicação determinística.
- P6.S10 com outputs V2 e projeção temporária P7 V1.
- S4, S5 e S6 declaradas como capabilities não operacionais no modo `TEMPLATE_ONLY`; não produzir sucesso fictício.

### Templates da Onda 1

- long/short underlying quando suportado;
- long call e long put;
- debit vertical;
- defined-risk credit vertical;
- long straddle e long strangle;
- long butterfly e long condor;
- iron butterfly e iron condor;
- collar;
- risk reversal somente com risco definido;
- protected ratio somente quando maximum loss finito for provado.

### Fora da Onda 1

- calendars e diagonals;
- mutação livre;
- target payoff avançado;
- inverse design;
- MILP/beam/local/evolutionary search;
- ambiguity optimization;
- quality-diversity avançada;
- margem exata de corretora;
- gestão dinâmica ou hedging da P8.

### Gates

- W1-G00: baseline, hash, clean extraction e testes antigos.
- W1-G01: domínio e schemas únicos; zero modelos concorrentes.
- W1-G02: PIT e future-perturbation non-interference.
- W1-G03: contratos e quotes reais; zero phantom instruments.
- W1-G04: payoff analítico das estratégias conhecidas.
- W1-G05: defined risk e maximum-loss proof.
- W1-G06: custos e liquidez por perna e weakest-leg rule.
- W1-G07: IDs invariantes à ordem, escala separada da forma e dedup determinístico.
- W1-G08: publicação V2 e projection P7 V1.
- W1-G09: Ruff, mypy strict no núcleo, Hypothesis, replay e manifests.

## Onda 2 — Advanced Synthesis

### Objetivo

Adicionar deformação, target payoff, otimização inversa, cenários robustos e preservação de diversidade sem transformar a P6 em P7 ou P8.

### Escopo obrigatório

- P6.S4: registry de operadores, mutação local, trace e complexity budget.
- P6.S5: target payoff, market-implied state, regularização e qualification gate.
- P6.S6: replication basis, continuous relaxation, MILP open-source, beam search, local search e solver portfolio.
- P6.S7: pathwise valuation quando possível, ambiguity evaluation e Greeks opcionais.
- P6.S8: suporte aprofundado a multi-expiry, American-option policy e margin proxies mais ricos.
- P6.S9: equivalence clustering e quality-diversity archive determinístico.
- P6.S10: P5 V2 adapter final, P7 V2 native handoff, V1 projections isoladas.

### Challenger não bloqueante

- evolutionary search;
- learned proposer;
- neural surface;
- solvers comerciais;
- Wasserstein ambiguity sem calibração de raio.

### Gates

- W2-G01: mutações preservam genealogia e respeitam budgets.
- W2-G02: target payoff finito, regularizado e semanticamente qualificado.
- W2-G03: solvers respeitam universo, constraints, timeout e status.
- W2-G04: deterministic replay e equivalência econômica.
- W2-G05: cenários nominais e ambiguity sets reconciliados.
- W2-G06: calendars/diagonals bloqueiam quando lifecycle não é modelável.
- W2-G07: QD mede cobertura, não produz ranking geral.
- W2-G08: golden P5 V2 → P6 → P7 V2.

## Estratégia para a P5 em modificação

- Não acoplar a Onda 1 ao schema transitório da P5.
- Definir uma porta semântica `MarketBeliefBundle` com capabilities explícitas.
- Usar fixtures contratuais próprias da P6 durante a Onda 1.
- Implementar o adapter da P5 final somente após o contrato V2 ser congelado.
- Ausência de scenario, ambiguity, dependence ou surface deve ser `UNAVAILABLE`, nunca reconstruída por default.

## Migração da RC5.10

- Preservar os kernels válidos de PIT, lifecycle, chain integrity, superfície, liquidez, Greeks, cenário e certificação.
- Re-hospedar os serviços nos novos domínios; não copiar e manter versões paralelas.
- Substituir atomic candidates por `StrategyCandidate` multi-leg canônico.
- Manter golden parity para os candidatos single-leg da RC5.10.
- Remover o modelo interno V1 após a projeção ser isolada na fronteira P7.

## Definition of Done

A conclusão exige software, temporal, market, strategy, scenario, solver e compatibility closure. `production_promotion_allowed` permanece `false` até chain real qualificada, pricing validado, margin rules, execution calibration, monitoramento e aprovação independente.
