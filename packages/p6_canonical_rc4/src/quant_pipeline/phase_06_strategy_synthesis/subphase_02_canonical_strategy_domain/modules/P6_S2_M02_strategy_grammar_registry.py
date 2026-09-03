"""P6.S2.M02 wrapper."""

from ..runner_support import grammar

MODULE_ID = "P6.S2.M02"


def run(inputs, context, configuration):
    return grammar(inputs, context, configuration)
