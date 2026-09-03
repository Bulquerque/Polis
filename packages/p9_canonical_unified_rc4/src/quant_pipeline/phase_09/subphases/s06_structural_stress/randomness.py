from __future__ import annotations

import hashlib

import numpy as np
from numpy.random import Generator, SeedSequence

from .contracts import NonEmptyStr, SeedPolicy


def _token_words(token: str) -> list[int]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return [int.from_bytes(digest[offset : offset + 4], "big") for offset in range(0, 32, 4)]


def derive_seed_sequence(policy: SeedPolicy, *tokens: NonEmptyStr | str | int) -> SeedSequence:
    entropy: list[int] = [policy.root_entropy]
    for token in tokens:
        if isinstance(token, int):
            entropy.append(token)
        else:
            entropy.extend(_token_words(str(token)))
    return SeedSequence(entropy)


def derive_generator(policy: SeedPolicy, *tokens: NonEmptyStr | str | int) -> Generator:
    return np.random.default_rng(derive_seed_sequence(policy, *tokens))
