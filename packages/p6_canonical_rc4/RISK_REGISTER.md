# Risk Register — RC6.0-C

| Risco | Estado atual | Controle |
|---|---|---|
| Branches não exercitados | Fechado localmente: 100% de 796 branches | coverage gate obrigatório |
| Regressão de contratos | 55 módulos/10 subfases validados | contract validator + golden integration |
| Instrumentos fantasma | Bloqueado por lifecycle, snapshot PIT e basis validation | testes adversariais |
| Explosão combinatória | Presente por natureza em modos avançados | budgets, node caps, timeout e publication cap |
| Solver interpretado como ótimo global | Risco de comunicação | status e diagnósticos explícitos; busca inteira é limitada |
| American exercise/assignment | Não qualificado integralmente | bloquear/degradar estruturas não suportadas |
| Margem exata | Indisponível sem clearing/corretora | upper bound/proxy conservadora + status |
| Dados reais e execução | Não qualificados nesta release | production promotion permanece false |
| Mudança futura da P5/P7 | Contratos finais ainda não congelados | semantic ports e adapters explícitos |
| Ferramentas externas de lint/type/property | Ruff, mypy e Hypothesis indisponíveis offline | gates internos executados; dívida declarada |
