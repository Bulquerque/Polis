"""P6.S2.M05 wrapper."""

from ..runner_support import identity

MODULE_ID = "P6.S2.M05"


def run(inputs, context, configuration):
    return identity(inputs, context, configuration)
