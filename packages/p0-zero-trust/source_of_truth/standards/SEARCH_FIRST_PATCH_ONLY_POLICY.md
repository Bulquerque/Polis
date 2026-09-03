# Search-First Patch-Only Policy

Todo agente deve seguir esta ordem antes de alterar qualquer pacote:

1. Procurar arquivo, função, contrato, schema ou teste equivalente já existente.
2. Editar o menor trecho possível no arquivo existente.
3. Criar arquivo novo apenas se não existir local canônico adequado.
4. Registrar qualquer arquivo novo no `MANIFESTO.csv`.
5. Atualizar registry/contrato/schema/teste quando a mudança afetar interface.
6. Falhar se a mudança introduzir duplicação crítica ou conexão proibida.

## Proibições

- Criar `utils.py` ou `helpers.py` genérico sem responsabilidade clara.
- Recriar função comum de hash, schema, contrato, logging, manifest ou loading YAML dentro de fases.
- Criar arquivo monolítico para resolver problema local.
- Alterar contrato global sem atualizar changelog e relatório de impacto.
