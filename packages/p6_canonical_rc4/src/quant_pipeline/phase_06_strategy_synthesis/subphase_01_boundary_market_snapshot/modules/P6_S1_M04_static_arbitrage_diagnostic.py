"""P6.S1.M04 module wrapper."""

from ..runner_support import diagnose_arbitrage

MODULE_ID = "P6.S1.M04"


def run(inputs, context):
    return diagnose_arbitrage(inputs, context)
