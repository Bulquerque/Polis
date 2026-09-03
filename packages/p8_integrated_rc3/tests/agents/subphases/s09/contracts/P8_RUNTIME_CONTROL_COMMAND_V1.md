# P8_RUNTIME_CONTROL_COMMAND_V1

The canonical schema is `schemas/runtime_control_command.schema.json`.

Commands are declarative control modes, not broker orders. Consumers must apply them through their own state machine and return a consumption receipt.

Required properties:

- stable command and idempotency IDs;
- reason codes;
- issued and expiry clocks;
- allowed action vocabulary;
- feasibility status.
