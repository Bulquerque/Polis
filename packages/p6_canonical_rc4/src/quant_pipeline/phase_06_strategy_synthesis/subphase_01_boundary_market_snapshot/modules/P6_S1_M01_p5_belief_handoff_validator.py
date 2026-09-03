"""P6.S1.M01 module wrapper."""

from ..runner_support import validate_beliefs

MODULE_ID = "P6.S1.M01"


def run(inputs, context, configuration=None):
    return validate_beliefs(inputs, context, configuration)
