# Canonical Zero Trust Rules — V14.1 RC4.1

A Fase 0 é a Guardiã Zero Trust.

## Regras

- Qualquer conexão não listada é proibida.
- Todo artefato precisa de schema, lineage e hash quando materializado.
- Toda fase reporta status técnico para a Fase 0.
- A Fase 0 pode bloquear, auditar e registrar; não pode executar lógica econômica.
- Feedback da Fase 0 é técnico, não econômico.
- Nenhuma fase pode criar artefato de fase futura.
- Nenhum módulo pode usar target em inferência.
