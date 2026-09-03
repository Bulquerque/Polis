"""Versioned deterministic random streams."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
from scipy.stats import qmc


@dataclass(frozen=True, slots=True)
class RandomStream:
    entropy: int
    namespace: str

    def _spawn_key(self) -> tuple[int, ...]:
        digest = hashlib.sha256(self.namespace.encode("utf-8")).digest()
        return tuple(int.from_bytes(digest[i:i+4], "big") for i in range(0, 16, 4))

    def generator(self) -> np.random.Generator:
        sequence = np.random.SeedSequence(self.entropy, spawn_key=self._spawn_key())
        return np.random.Generator(np.random.PCG64DXSM(sequence))

    def sobol_uniforms(self, dimension: int, count: int) -> np.ndarray:
        seed = int(self.generator().integers(0, 2**31 - 1))
        engine = qmc.Sobol(d=dimension, scramble=True, seed=seed)
        exponent = int(np.ceil(np.log2(count)))
        return engine.random_base2(exponent)[:count]
