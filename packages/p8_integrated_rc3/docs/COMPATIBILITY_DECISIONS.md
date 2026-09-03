# Decisões de Compatibilidade

## CD-001 — Uma wheel
A release final é uma distribuição única. Isso elimina shadowing entre source roots e torna a ordem de instalação irrelevante.

## CD-002 — Package surface
`quant_pipeline` permanece namespace. `quant_pipeline.phase_08_portfolio_control` é um pacote regular intencional. O teste histórico que exigia essa segunda camada como namespace foi reescrito para verificar a arquitetura consolidada.

## CD-003 — Python e dependências
A restrição mais forte entre os componentes foi adotada: Python `>=3.13,<3.15`, Pydantic `>=2.13,<3`. NumPy, SciPy, PyYAML e jsonschema foram alinhados às maiores restrições comuns.

## CD-004 — Sem merge de modelos concorrentes
Contratos históricos foram preservados em seus domínios. Traduções acontecem na anti-corruption layer; não se criou um super-payload universal.

## CD-005 — Facades históricas
Nomes internos ligados aos agentes não são parte da API canônica. Permanecem para compatibilidade de RC0 e devem ser deprecados gradualmente, depois que consumidores migrarem.

## CD-006 — S2 currency ownership
A moeda é propriedade do candidato normalizado. O adapter não tenta lê-la da perna.

## CD-007 — A5 audit projection
S10 trabalha com uma ordem por instrumento; S7 pode possuir ordem multi-leg. A projeção cria records por perna e preserva o ID original em campos `source_*`.

## CD-008 — Runtime control
O contrato anterior mínimo foi estendido de forma aditiva. Campos antigos continuam válidos; campos de hash, sequência, idempotência e feasibility estão disponíveis para a integração robusta.
