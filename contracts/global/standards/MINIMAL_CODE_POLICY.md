# Minimal Code Policy

O projeto deve privilegiar pouco código, código limpo e funções pequenas.

## Regras

1. Preferir função simples e pura a classe quando não houver estado real.
2. Não criar abstração antes de existir repetição real.
3. Cada função deve ter uma responsabilidade.
4. Cada arquivo deve pertencer a uma subfase clara.
5. Código comum transversal deve ficar em `quant_pipeline.common`.
6. Código econômico específico deve ficar dentro da fase correspondente.
7. Nenhum módulo de fase deve importar módulo interno de fase posterior.
8. Toda exceção precisa ser explícita e registrada.

## Limites padrão

- Python file: 350 linhas.
- Função: 60 linhas.
- Classe: 180 linhas.
- YAML de contrato: 300 linhas.
- Markdown operacional: 600 linhas.
