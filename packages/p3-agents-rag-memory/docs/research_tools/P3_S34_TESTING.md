# P3.S34 Testing Guide

## Testes focados

```bash
pytest -q tests/phase_specific/research_tools/test_p3_s34_*.py -p no:cacheprovider
```

## Cobertura funcional

- 19 capacidades e quatro categorias;
- requisitos derivados das 34 operações;
- duas personas com perfis contrastantes;
- rejeição recursiva de campos futuros/performance;
- oito planos DAG e limite de cinco chamadas;
- readiness e bloqueio upstream;
- projeção exata S21;
- JSON Schemas Draft 2020-12;
- diferenças de modos entre varejo e institucional;
- projeção S16→S21;
- projeção S20→S21;
- token budget;
- igualdade `as_of == decision_time`;
- determinismo e wrappers.

## Propriedades críticas

```text
mais competência não cria nova ferramenta: amplia modos permitidos
view bloqueada remove a operação
campo futuro no perfil bloqueia o build
mesmo input produz o mesmo hash
nenhum plano supera cinco chamadas visíveis
contexto final nunca supera o token budget
```
