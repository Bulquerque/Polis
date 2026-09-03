# P0.S2 — Contract & Schema Gate

## Função

A P0.S2 é a fronteira de contratos e tipos do control plane Zero Trust. Ela garante que módulos, artefatos e conexões usem contratos canônicos, schemas válidos, interfaces compatíveis, campos semanticamente permitidos e formatos físicos coerentes com a política declarada.

Ela mantém cinco responsabilidades públicas, preservadas nos IDs originais:

1. **P0.S2.M01 — Contract Registry Builder**: materializa o inventário canônico de contratos e seus bindings de I/O e schemas.
2. **P0.S2.M02 — Schema Registry Builder**: materializa o inventário canônico de schemas, valida autoridade/mirrors e normaliza metadados estruturais.
3. **P0.S2.M03 — Input/Output Compatibility Checker**: verifica compatibilidade producer→consumer e compatibilidade semântica recursiva dos schemas.
4. **P0.S2.M04 — Forbidden Field Scanner**: aplica políticas globais e específicas por fase, com contexto explícito de treino/inferência quando disponível.
5. **P0.S2.M05 — Artifact Format Policy Validator**: valida política de formato, extensão e conteúdo físico sem duplicar a autoridade de hash da P0.S3.

## Princípios da reforma

- Os IDs `P0.S2.M01` a `P0.S2.M05` e a interface pública `run_module(inputs, config=None)` foram preservados.
- A arquitetura externa de contratos YAML, schemas e módulos 1:1 foi preservada.
- Funções privadas da P0.S1 deixaram de ser dependências da implementação da S2.
- Contagens e versões que podem ser derivadas de autoridades canônicas deixaram de ser hardcoded onde isso era seguro.
- A lógica interna foi dividida em componentes privados específicos da S2, evitando `helpers.py`/`utils.py` genéricos.
- Arquivos reformados respeitam o limite de 350 linhas e funções respeitam o limite de 60 linhas.
- A compatibilidade semântica passou a inspecionar estruturas aninhadas, arrays e constraints declaradas pela autoridade.
- O scanner de campos proibidos passou a considerar políticas específicas de cada fase e contexto explícito antes de heurísticas por nome/path.
- O validador de formatos passou a verificar conteúdo real para YAML/JSON/JSONL/CSV/Markdown/Mermaid/PNG/Parquet, conforme a política.

## Limite desta entrega isolada

Esta entrega reforma **somente a P0.S2**. Os relatórios de M03, M04 e M05 permanecem com seus nomes e contratos públicos atuais e estão prontos para integração posterior no pacote de evidências e na Control Tower. O rewiring de P0.S4/P0.S6 não foi incluído para evitar alterar outras subfases nesta entrega.

## Não faz

Não processa dado econômico, não cria feature, não prevê, não ranqueia, não monta carteira, não executa trade, não altera backtest e não corrige automaticamente outras fases.
