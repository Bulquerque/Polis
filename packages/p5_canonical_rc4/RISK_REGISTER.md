# Risk register

| Risk | State | Mitigation |
|---|---|---|
| real repository P4/P6 receipts not executed | external pending | integration change set and native P6 contract test |
| full V2 manifest not yet consumed by P6 RC6.0-C | downstream pending | native belief remains supported; manifest declares pending support |
| static/property tooling unavailable | external pending | pyproject configuration and CI commands |
| simplified weekday calendar baseline | documented | injectable `TradingCalendarPort` |
| optional surface/IV/liquidity absent | explicit unavailable | no synthetic default |
| model/scenario performance on real data unknown | production blocker | prospective qualification required |
| live drift/incident recovery absent | production blocker | keep promotion false |
