# Source of Truth — P3.S35

## Autoridades

1. Modelos Pydantic em `extensions/research_tools/families/corpus/` são a autoridade dos contratos serializados.
2. `config/research_tools/corpus/*.yaml` é a autoridade das políticas operacionais.
3. JSON Schemas em `schemas/research_tools/corpus/` são derivados dos modelos, nunca editados manualmente.
4. Contratos de módulo em `contracts/modules/` definem inputs, outputs, conexões e limites de responsabilidade.
5. `contracts/MODULE_REGISTRY_OVERLAY.yaml` e `config/CANONICAL_DAG_OVERLAY.yaml` são as autoridades aditivas de registro e execução.
6. `FILE_MANIFEST.json` e `MANIFESTO.csv` são autoridades de integridade do pacote.

## Escopo congelado

```text
Subfase: P3.S35
Módulos: P3.S35.M01–P3.S35.M05
Família: research.corpus.v1
Operações: 6
Versão: 1.0.0
```

## Não autoridades

- documentos históricos de planejamento fora deste ZIP;
- um MCP externo não configurado;
- índices live;
- caminhos de arquivos fornecidos por requests;
- respostas geradas pelo LLM sem schema e evidência.
