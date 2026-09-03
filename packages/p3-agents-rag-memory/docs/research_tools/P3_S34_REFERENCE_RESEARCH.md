# P3.S34 Reference Research

## Agentes e ferramentas

- Yao et al., **ReAct: Synergizing Reasoning and Acting in Language Models**. Fundamenta a alternância entre raciocínio e chamadas de ferramentas.
- Schick et al., **Toolformer: Language Models Can Teach Themselves to Use Tools**. Fundamenta requests estruturados e incorporação controlada de respostas.
- Karpas et al., **MRKL Systems**. Fundamenta famílias especializadas atrás de um roteador comum.
- ReAct official reference implementation: `https://github.com/ysymyth/ReAct`.

## Recursos limitados

A literatura de rational inattention e bounded rationality trata informação e processamento como recursos custosos. Na S34 isso é aplicado por:

- orçamento de chamadas;
- research time;
- computational access;
- acesso público/profissional;
- modos por operação;
- downgrade explícito.

## Contratos

- JSON Schema Draft 2020-12: `https://json-schema.org/draft/2020-12`.
- Pydantic strict mode: `https://docs.pydantic.dev/latest/concepts/strict_mode/`.
- MCP tools specification: `https://modelcontextprotocol.io/specification/2025-11-25/server/tools`.
- MCP Python SDK: `https://github.com/modelcontextprotocol/python-sdk`.

MCP é tratado como protocolo de exposição/transporte. A identidade funcional continua sendo `tool_id + operation_id`.
