# P9 RC2 — Correção dos bloqueadores da RC1

## Escopo

A RC2 corrige os bloqueadores encontrados na auditoria módulo a módulo da RC1. As correções foram aplicadas como mudanças contratuais explícitas, sem relaxar gates ou fabricar evidência.

## Correções

| Finding | Correção RC2 | Prova |
|---|---|---|
| IPS com denominador incorreto | IPS divide pela população logada total; SNIPS mantém denominador normalizado | oracles com ação de probabilidade-alvo zero |
| DR falhava em ação-alvo zero | propensity só é obrigatória quando a probabilidade-alvo é positiva | teste sem propensity na linha de peso zero |
| Receipts aceitavam hash falso | receipts recalculam o payload hash no `model_validator` | teste adversarial de tampering |
| Bundles S5/S6 aceitavam hash falso | ambos verificam o hash do preimage canônico ao desserializar | fixtures adulteradas rejeitadas |
| S4→S5 misturava execuções | contrato V2 vincula run/cycle/configuration, bundle, painel, quality receipt e inputs estatísticos | teste negativo com identidade divergente |
| S6→S7 perdia identidade/AUM | envelope V2 preserva bundle, clocks, configuração, evidência e AUM content-addressed | tampering e PIT tests |
| S8→S9 aceitava outro ciclo | source context V2 vincula run, cycle, attribution hash e configuration set | teste negativo de ciclo divergente |
| S2→S3 era lossy | plano V2 preserva assigned/reserved, DAG, fidelity, resources, estados e idempotência | conservation test |
| Sem orquestrador S1→S10 | `P9CycleRunner` fail-closed com checkpoints e receipt content-addressed | sete golden terminal states |
| Canonicalização dispersa nas fronteiras | adapters V2 usam `P9-C14N-JSON-1`; registry canônico documenta versões | registry validator |
| Reason codes sem autoridade global | registries globais de tokens, reason codes e contratos | gate estrutural |
| `assert` em produção | substituídos por exceções de domínio | source scan |
| Timeout apenas pós-fato | controlador POSIX preemptivo e clock/controller injetáveis | teste de interrupção real |
| Build não reproduzido | wheel RC2 construída sem isolamento e importada a partir da wheel instalada | wheel/import qualification |

## Limites preservados

- A RC2 prova integração técnica e contratual, não vantagem econômica prospectiva.
- `ruff` e `mypy` não estavam disponíveis no registry do ambiente. O pacote mantém as configurações e executa gates AST, line length, broad exceptions, imports, registries e schemas. Esses dois executáveis continuam recomendados no CI conectado.
- Instalação de dependências em um virtualenv totalmente vazio depende de um wheelhouse/index provisionado. A wheel da P9 foi instalada com `--no-deps` em target limpo e importada contra as dependências qualificadas registradas.
