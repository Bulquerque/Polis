# Canonical Testing Standards — V14.1 RC4.1

## Separação de responsabilidade

A Fase 0 mantém testes globais e estruturais.
As fases 1–9 mantêm somente testes específicos da fase.

## Testes globais da Fase 0

- Estrutura de pacote.
- Ausência de cache.
- Ausência de `TBD`.
- YAML válido.
- Manifesto cobre arquivos.
- Sem conexão proibida.
- Sem arquivo monolítico.
- Sem duplicação crítica.
- Compatibilidade output/input entre fases.

## Testes locais da fase

- Contrato específico da fase.
- Schema específico da fase.
- Regras anti-leakage da fase.
- Validações específicas de módulos.
- Fixtures mínimas de input/output da fase.

## Regra

Não duplicar teste estrutural global dentro de todas as fases.
