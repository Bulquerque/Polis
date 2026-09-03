# Known limitations

- EWMA/CUSUM are transparent champion monitors, not a claim of universal optimal change detection.
- Thresholds and false-alarm budgets require calibration on qualified point-in-time data before production use.
- Runtime control commands are declarative; safe application depends on the S7/S8 consumer state machine and its receipt.
- The invariant snapshot is a closed V1 contract; additional Greeks, concentration and venue-specific invariants require a contract version change.
- Shadow evaluation proves no execution authority inside this package, but full system safety also requires the external adapter to expose no broker port.
- P8.S9 does not authorize production or promote challengers. `production_promotion_allowed` is always false.
- RC4.1 generic reports are not byte-compatible and need an explicit adapter.
