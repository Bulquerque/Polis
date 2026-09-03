# Plano de testes e qualificação

## Contratos
Schemas, produtores, versões, campos proibidos e falhas de manifestos.

## Temporalidade
Vintages macro, publicação tardia, timezone, corporate actions, janela de fit, late-arriving data e reprodução as-of.

## Numérico
Oracle independente para cada observador, propriedades de escala, splits, ausência de futuro e testes metamórficos.

## Hipóteses
Passaporte válido, duas parametrizações no máximo, família correta e registro de toda tentativa.

## Representação
PCA/Sparse PCA real, loadings, estabilidade; encoder cross-fitted, não colapsado e comparado apenas às duas configurações autorizadas.

## Segurança operacional
Nenhum Python legado é importado na validação documental. Execuções futuras usam timeout, processo isolado e alvo explícito.

## Cross-phase
P2→P4, P3→P4, N+1, P4→P5 e recibo de consumidor. Qualificação econômica permanece em P5/P9.
