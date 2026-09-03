"""P6.S1.M05 module wrapper."""

from ..runner_support import build_market_snapshot

MODULE_ID = "P6.S1.M05"


def run(inputs, context):
    return build_market_snapshot(inputs, context)
