# Warm-up and replay

Warm-up calls the same runtime kernel used by live cycles, with live providers and external outputs disabled. Each historical step produces a closure and checkpoint. Replay consumes frozen provider/tool results and must reproduce equivalent artifact hashes for deterministic components.
