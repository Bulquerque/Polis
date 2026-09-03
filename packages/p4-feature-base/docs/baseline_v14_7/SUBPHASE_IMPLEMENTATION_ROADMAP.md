# Roadmap de implementação por subfase

## Sequência obrigatória

### Onda 0 — Fechamento contratual
Congelar schemas, IDs, grains, timestamps, passaportes, campos proibidos e manifestos. Nenhum agente econômico começa antes deste gate.

### Onda 1 — P4.S1 e P4.S2
Implementar fronteira, autenticidade, temporalidade, entidades, revisões, missingness e painel canônico. São o caminho crítico de toda a fase.

### Onda 2 — P4.S3
Implementar registro de fenômenos, DSL, operadores e gate de orçamento. Essa subfase permite que as fábricas seguintes sejam paralelizadas sem criar fórmulas incompatíveis.

### Onda 3 — P4.S4
Implementar observações atômicas em paralelo por modalidade, cada uma com oracles independentes. O módulo fundamental depende de novos contratos point-in-time da P2.

### Onda 4 — P4.S5
Implementar as dez fábricas de perspectivas. Cada agente recebe apenas os passaportes e observadores da sua família.

### Onda 5 — P4.S6 e P4.S7
Alinhar views, medir conflito, criar somente interações autorizadas, normalizar e selecionar estruturalmente.

### Onda 6 — P4.S8
Entregar primeiro PCA/Sparse PCA. O encoder só é iniciado após o gate de necessidade e usa a arquitetura única pré-registrada.

### Onda 7 — P4.S9
Fechar lineage, drift, views de consumidores, ledger e handoff P5. Executar recibo real da P5 e validação P0.

## Paralelização segura

- S4.M01–M08 podem rodar em paralelo depois de S1–S3 congeladas.
- S5.M01–M10 podem rodar em paralelo depois dos outputs atômicos e do registry.
- S8.M02 e S8.M03 não devem disputar promoção: Sparse PCA é champion fixo, encoder é challenger.
- S9 é integrada por um único agente de garantia para evitar divergência de lineage.
