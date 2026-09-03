"""P5/P6/P7 RC3 compatibility boundary for native P8 contracts."""

from .adapter import (
    ADAPTER_ID,
    ADAPTER_RELEASE,
    P567RC3Adapter,
    P567RC3CompatibilityError,
    adapt_p567_rc3_to_p8,
)
from .models import P567RC3AdaptationReceiptV1, P567RC3AdaptationResult, SourceArtifactAuditRecord

__all__ = [
    "ADAPTER_ID",
    "ADAPTER_RELEASE",
    "P567RC3Adapter",
    "P567RC3CompatibilityError",
    "P567RC3AdaptationReceiptV1",
    "P567RC3AdaptationResult",
    "SourceArtifactAuditRecord",
    "adapt_p567_rc3_to_p8",
]

from .live_release import build_limited_p9_release
