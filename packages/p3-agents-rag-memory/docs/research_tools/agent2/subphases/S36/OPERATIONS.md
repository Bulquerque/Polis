# Operations

## Mercado

### `get_snapshot`
Última observação visível, staleness, origem e qualidade.

### `get_history`
Histórico ordenado e limitado. `RAW` é o padrão. Ajustes PIT só serão liberados quando o upstream fornecer uma política inequívoca e comprovada.

### `get_liquidity`
Volume, volume financeiro, spread relativo, tradability, missingness e score existente. Não estima impacto oficial.

### `get_corporate_actions`
Ações conhecidas até a decisão, separando anúncio, efetivação, ex-date, record date e pagamento.

### `compare_instruments`
Normalização e retorno cumulativo descritivos. Não classifica nem recomenda.

## Opções

### `get_contracts`
Contratos conhecidos e ainda válidos no instante histórico.

### `get_chain_snapshot`
Última quote visível por contrato, com filtros de vencimento, tipo e executabilidade.

### `get_quote_history`
História PIT por `contract_key`, com limite por contrato.

### `get_surface_diagnostics`
Cobertura, skew observado, term structure observada e testes estáticos aparentes. Sem interpolação, solver ou recomendação.
