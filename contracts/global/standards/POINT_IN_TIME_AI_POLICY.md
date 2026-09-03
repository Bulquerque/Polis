# Política point-in-time para fontes e modelos

Status: `canonical_rc4_1`

Canonical temporal rules:

- `as_of_date` is the simulated decision date.
- `provider_available_from` and `provider_available_until` define provider availability.
- `available_at` is the earliest time a data point, document, or capability could be known.
- `effective_from` and `effective_until` define the project simulation validity window.
- Data and documents require `available_at <= as_of_date`.
- Models require exact identifier, validated capability, official evidence, license evidence,
  and a versioned smoke test.
- Model eligibility requires provider availability, effective validity, and validated capability
  at `as_of_date`.
- Fallbacks must not cross into the future, silently replace evidence, or mix providers without
  a new snapshot and validation trail.

Toda execução histórica deve separar `as_of_date`, a janela de disponibilidade do provedor e `available_at`.
Dados e documentos só podem ser usados quando `available_at <= as_of_date`.
Modelos exigem capacidade validada, identificador exato, licença, evidência oficial e smoke test versionado.
Fallbacks não podem cruzar para o futuro nem trocar silenciosamente o conjunto de evidências.
