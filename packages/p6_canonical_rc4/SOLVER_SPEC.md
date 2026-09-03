# Solver Specification

A interface interna recebe `StrategySynthesisProblem` e retorna `SolverResult`. Nenhum solver publica diretamente no artifact store oficial.

Implementações:

- relaxação contínua por coordinate descent não negativo;
- busca inteira limitada ao neighborhood da solução contínua, com node/time caps;
- beam search determinística;
- local search determinística;
- challenger evolutivo com seed fixa, population/generation budgets e repair de leg count.

`TIMEOUT` nunca é rotulado como `OPTIMAL`. O status `OPTIMAL` da busca inteira significa ótimo apenas dentro do neighborhood discreto e budgets declarados; não representa prova global de um MILP geral.
