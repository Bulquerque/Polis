# P8_STATEFUL_EVIDENCE_BUNDLE_V1

Contrato consumido por `P8.S10.M01`.

Inclui:

- candidate universe e estado terminal por candidato;
- initial/final positions;
- orders e fills;
- virtual-to-physical allocations;
- cash, premium, costs, margin, collateral e liabilities;
- valuation, mark quality, NAV/PnL;
- ordered replay events e checkpoint hash;
- references content-addressed de S1–S9.

## Invariantes

- candidate IDs são únicos e conservados;
- order total = filled + cancelled + rejected + open;
- fills referenciam uma ordem compatível;
- final position = initial position + signed fills;
- virtual allocations fecham com physical positions;
- final cash fecha com cash flow + premium + costs;
- margin/collateral/liabilities fecham em ledgers separados;
- marks ausentes não viram zero;
- event sequence é ordenada e replayável.
