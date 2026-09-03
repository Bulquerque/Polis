# Guia de integração

## 1. Pré-requisitos

- pacote P3 RC4.1 disponível;
- Python 3.12 ou superior;
- Pydantic 2.x;
- artefatos `retrieval_index_manifest` e `phase3_run_snapshot` de S12/S2;
- `artifact_store` injetado em `ModuleExecutionContext.services` para M01.

## 2. Merge

Copie o conteúdo de `src/` para o `src/` da P3, preservando os caminhos. Copie também:

```text
contracts/modules/P3_S35_*.yaml
contracts/MODULE_REGISTRY_OVERLAY.yaml
config/CANONICAL_DAG_OVERLAY.yaml
subphases/P3_S35_corpus_research_tool_suite.md
config/research_tools/corpus/
schemas/research_tools/corpus/
```

Não substitua módulos `P3.S1–P3.S31`.

## 3. DAG

Ordem de bootstrap:

```text
P3.S12.M02 retrieval_index_manifest_builder
        ↓
P3.S35.M01 corpus_snapshot_index_loader
        ↓
P3.S35.M02 hybrid_retrieval_policy_builder
        ↓
P3.S35.M03 document/version/provenance bundle
P3.S35.M04 counterevidence/timeline bundle
        ↓
P3.S35.M05 consolidated qualification bundle
        ↓
P3.S40 handler registry and ToolGatewayPort bridge
```

## 4. Serviços

M01 requer:

```python
ModuleExecutionContext(services={"artifact_store": artifact_store})
```

O runtime das operações é construído com `create_corpus_runtime_bundle(...)` e recebe portas opcionais para:

- recuperação densa;
- reranking;
- resolução de bytes P1;
- proveniência P1/P2.

Nenhuma dessas portas pode usar rede no perfil de backtest.

## 5. S21

`CorpusToolResultEnvelope.model_dump(mode="json")` é colocado em `ToolExecutionResponse.canonical_payload`.

Na ponte inicial, `ToolExecutionResponse.evidence_refs` permanece vazio; o S21 adiciona a referência sintética `tool:<execution_id>`. As evidências detalhadas permanecem no envelope para S40, P4 e P9.

## 6. Qualificação

- lexical + PIT: qualificado local;
- semântico/reranker ausentes: capacidade opcional indisponível, não falha do baseline;
- `FORENSIC` sem grafo de versões: `BLOCKED_UPSTREAM`;
- proveniência sem P1: `DEGRADED`;
- bytes brutos inválidos: fallback explícito e `DEGRADED`.


## 7. Registro canônico

O registry original da P3 é congelado em 81 módulos. Este pacote não o sobrescreve. A composição final da extensão deve aplicar `contracts/MODULE_REGISTRY_OVERLAY.yaml` de forma aditiva e validar que nenhum ID existente foi substituído.

O mesmo princípio vale para `config/CANONICAL_DAG_OVERLAY.yaml`: ele declara as dependências novas sem renumerar ou reescrever os módulos existentes.
