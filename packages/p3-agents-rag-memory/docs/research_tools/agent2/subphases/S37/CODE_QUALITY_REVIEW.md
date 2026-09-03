# Revisão de qualidade de código

## Padrões aplicados

- modelos Pydantic estritos, congelados e `extra=forbid`;
- portas pequenas e tipadas;
- handlers por operação;
- fachadas pequenas para preservar imports públicos;
- wrappers finos;
- hashes canônicos;
- ausência de estado global mutável;
- ausência de rede e relógio local no domínio;
- nenhuma captura genérica de exceção no código de domínio;
- imports em camadas verificados por AST.

## Métricas finais

- 34 arquivos Python;
- nenhum arquivo acima de 300 linhas lógicas;
- nenhuma função acima de 50 linhas;
- nenhuma função acima da complexidade de revisão 12;
- nenhuma linha acima de 110 caracteres;
- cobertura branch-aware de 83%.

Detalhes executáveis ficam em `reports/STATIC_ANALYSIS.json`, `reports/STATIC_ANALYSIS.txt` e `reports/COVERAGE.txt`.

## Dependências obrigatórias

- Pydantic;
- PyYAML.

Recuperação de dados e APIs permanecem upstream. Nenhum framework de agentes ou biblioteca macro pesada foi adicionado.

## Limitações do ambiente

`ruff` e `mypy` não estavam instalados. Não há alegação de execução dessas ferramentas. A validação equivalente disponível utilizou compilação, AST, testes, coverage, build de wheel e import em instalação isolada.
