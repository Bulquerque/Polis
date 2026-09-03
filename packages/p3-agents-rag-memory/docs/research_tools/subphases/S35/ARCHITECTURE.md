# Arquitetura da P3.S35

## Responsabilidade

A subfase fornece pesquisa explícita e auditável sobre o corpus congelado da P3. Ela não substitui:

- chunking e indexação de S12;
- recuperação automática de contexto de S20;
- planejamento cognitivo de S21;
- binding de crenças e evidências de S22;
- gateway composto e qualificação final de S40.

## Fluxo

```text
S12 RetrievalIndexManifest
        ↓ valida hashes/snapshot
M01 CorpusIndexSnapshot + repository imutável
        ↓
M02 RetrievalPolicy + internal work budget
        ↓
M03 document/version/provenance handlers
M04 counterevidence/timeline handlers
        ↓
M05 consolidated handler manifest + qualification
        ↓
S40 runtime registry
        ↓
S21 ToolGatewayPort
```

## Camadas de código

```text
request_contracts.py       requests estritos
result_contracts.py        resultados, evidência, cobertura e PIT proof
index_contracts.py         snapshots, políticas e budgets
ports.py                   dependências externas
snapshot.py                adapter S12→S35
retrieval.py               seleção PIT, BM25, RRF e reranking opcional
provenance.py              conteúdo, versões e grafo P1→P2→P3
document_handlers.py       operações documentais
reasoning_handlers.py      contraprovas e timelines
qualification.py           operação × modo
factory.py                 composition root da família
```

## Decisões

- `tool_id`, provider e transporte são conceitos separados.
- A recuperação lexical é baseline obrigatório e determinístico.
- Recuperação densa e reranking são adapters opcionais.
- O filtro temporal ocorre antes de qualquer score.
- O índice S12 é verificado por hash e nunca reconstruído por S35.
- Handlers são read-only.
- O LLM escolhe operação e argumentos; cálculo, acesso e proveniência permanecem em código.
