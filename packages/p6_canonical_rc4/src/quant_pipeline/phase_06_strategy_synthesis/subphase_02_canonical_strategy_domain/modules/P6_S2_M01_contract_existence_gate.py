"""P6.S2.M01 wrapper."""

from ..runner_support import existence

MODULE_ID = "P6.S2.M01"


def run(inputs, context, configuration):
    return existence(inputs, context, configuration)
