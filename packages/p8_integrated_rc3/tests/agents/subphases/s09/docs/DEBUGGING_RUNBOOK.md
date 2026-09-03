# Debugging runbook

1. Validate the JSON request with `p8-s9 validate-request`.
2. Compare `context`, input hashes and policy version.
3. Inspect shift metric results and prior/next monitor states.
4. Inspect invariant violations before the selected fallback.
5. Verify fallback feasibility and allowed actions.
6. Confirm champion and challenger hashes are identical for a valid comparison.
7. Review adaptation rejection reason codes.
8. Replay with the same request bytes; output must be byte-stable after canonical serialization.
