# Execution flow

- S1–S4 validate inputs, freeze run identity and load governance.
- S5–S8 create and freeze the population and initial social graph.
- S9–S16 prepare warm-up, state, knowledge, memory and tools.
- S17–S20 resolve stimuli, activate persons and assemble context.
- S21–S24 execute cognition, tools, beliefs, state transitions and communication.
- S25–S28 update relations and memory, close the cycle and calculate society-level state.
- S29–S31 produce evidence, P4 features and P9 evaluation/learning outputs.

`DRY_RUN`, `WARMUP_REPLAY`, `REPLAY` and `LIVE` share one kernel policy. Only `LIVE` emits cross-phase outputs.
