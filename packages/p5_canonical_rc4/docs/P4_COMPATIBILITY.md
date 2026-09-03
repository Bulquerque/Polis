# P4→P5 compatibility matrix

| P4 V14.9 input | P5 handling | Wave 0–3 status |
|---|---|---|
| Feature handoff manifest | Locked hash/schema/topology validation | Implemented |
| Consumer view manifest and bundle | Reference-only materialization with declarative filters | Implemented |
| Feature availability | Explicit `available_at`; no decision-time fallback | Implemented |
| Optional views | Explicit unavailable/degraded capability | Implemented |
| Research passports and budgets | Structured bounded controls | Implemented |
| Future or duplicate grain | Fail-closed reason codes | Implemented |

P4 is not modified by this package.
