# P3.S32 API Compatibility

S32 não chama APIs externas. Ela modela providers e transportes. MCP e HTTP permanecem opcionais. No backtest, o catálogo canônico usa providers internos e nenhum provider externo é qualificado apenas por configuração estática.

## S15/S16

M03 aceita objetos Pydantic ou mappings dos contratos reais de S15/S16, remove qualquer material de segredo, preserva limites de orçamento e publica overlays novos sem mutar os inputs.

## Aliases

Aliases resolvem para uma operação canônica e proíbem segundo handler. Argumentos fixos são aplicados no runtime futuro, não no S32.
