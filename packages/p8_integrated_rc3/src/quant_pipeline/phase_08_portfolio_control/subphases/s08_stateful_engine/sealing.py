from __future__ import annotations

from .base_models import payload_hash
from .input_models import S7ToS8Handoff, S8InputBundle


def seal_s7_handoff(value: S7ToS8Handoff) -> S7ToS8Handoff:
    return value.model_copy(update={"content_sha256": payload_hash(value)})


def seal_s8_input(value: S8InputBundle) -> S8InputBundle:
    return value.model_copy(update={"content_sha256": payload_hash(value)})
