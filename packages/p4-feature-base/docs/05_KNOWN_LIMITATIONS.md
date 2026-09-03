# Known Limitations and External Qualification

The code is consolidated and integration-tested, but these items remain outside this release candidate:

1. P0 must register V14.9-RC1 in global module/subphase manifests.
2. P2 must formalize live `clean_fundamental_panel` and term-structure availability for full family coverage.
3. P5 must confirm its production receipt schema and consumer implementation.
4. Live providers, market calendars at full venue coverage and production-scale storage are not exercised here.
5. Encoder model-state externalization to a dedicated object store remains an infrastructure concern; the encoder is optional and disabled in the primary regression.
6. Some legacy S5/S6 qualification tests are computationally repetitive. They pass when isolated but are not the recommended fast CI path.
7. Production performance, memory and capacity qualification require representative universe/data volumes.

These limitations are explicit gates, not hidden fallbacks.
